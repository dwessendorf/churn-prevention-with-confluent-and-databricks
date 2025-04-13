import logging
import os
import json
import random
import uuid
from datetime import datetime
import time
from faker import Faker
import datetime
from dateutil.relativedelta import relativedelta
from datetime import date
from decimal import Decimal
import re
from confluent_kafka import Producer
import boto3
import yaml
from typing import Dict
import logging


########################################################################################
#  This python script creates synthetic data for car insurance policies. The data      #
#  contains artificial policy holder, car and tariff-details tuned for the german      # 
#  market. For the later creation of a churn prediction model it seeds some policy     # 
#  termination patterns into the data.                                                 #
########################################################################################

# Get the directory containing this script
__location__ = os.path.dirname(os.path.realpath(__file__))

# Configure logging
logging.basicConfig(level=logging.INFO)


# Initialize Faker for the German market
fake = Faker(["de-DE"])

# Initialize input data arrays on global level
car_list = []
car_weight_list = []
city_list = []
city_weight_list = []

########################################################################################
# Fetch secrets from AWS Secrets Manager
########################################################################################
def fetch_secret(secret_name: str) -> str:
    """Fetch a secret value from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

########################################################################################
# Kafka Producer Configuration
########################################################################################
def initialize_kafka_producer() -> Producer:
    """Initialize and return a Kafka producer."""
    # Fetch environment variables
    bootstrap_server = os.getenv("KAFKA_BOOTSTRAP_SERVER")
    kafka_topic_name = os.getenv("KAFKA_TOPIC_NAME")
    secret_name = os.getenv("SECRET_NAME")
    kafka_api_key_id = os.getenv("KAFKA_API_KEY_ID")
    
    # Fetch Kafka API secret from Secrets Manager
    kafka_api_key_secret = fetch_secret(secret_name)

    kafka_config = {
        "bootstrap.servers": bootstrap_server,
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "PLAIN",
        "sasl.username": kafka_api_key_id,
        "sasl.password": kafka_api_key_secret,
    }

    LOGGER.info(f"Kafka configuration initialized with topic: {kafka_topic_name}")
    return Producer(kafka_config), kafka_topic_name

########################################################################################
# Main Function: Produce Kafka Messages
########################################################################################
def lambda_handler(event, context):
    """Main Lambda function to produce Kafka records."""
    # Kafka initialization
    global car_list, car_weight_list, city_list, city_weight_list, region
    global LOGGER
    LOGGER = logging.getLogger(__name__)
    resp = {"status": False, "resp": ""}
    LOGGER.setLevel(logging.INFO)

    LOGGER.info(f"Initializing Kafka")
    producer, kafka_topic_name = initialize_kafka_producer()

    # Review generation configuration
    min_profiles = int(os.getenv("MIN_RECORDS_PER_RUN", "10"))
    max_profiles = int(os.getenv("MAX_RECORDS_PER_RUN", "20"))
    seconds_between_profiles = int(os.getenv("SECONDS_BETWEEN_REVIEWS", "1"))
    LOGGER.info(f"Loading Data files")
    
    # Fill input data arrays during first lambda initialization
    try:
        # Load all data
        if len(car_list) == 0: car_list = get_cars()
        if len(car_weight_list) == 0: car_weight_list = get_car_weights() 
        if len(city_list) == 0: city_list = get_cities() 
        if len(city_weight_list) == 0: city_weight_list = get_city_weights()
        
        # Ensure data arrays have matching lengths
        if len(car_list) != len(car_weight_list):
            LOGGER.warning(f"Adjusting car weights list length to match car list length")
            if len(car_list) > len(car_weight_list):
                # Extend weights list with the last weight
                last_weight = car_weight_list[-1] if car_weight_list else 1.0
                car_weight_list.extend([last_weight] * (len(car_list) - len(car_weight_list)))
            else:
                # Truncate weights list
                car_weight_list = car_weight_list[:len(car_list)]
        
        if len(city_list) != len(city_weight_list):
            LOGGER.warning(f"Adjusting city weights list length to match city list length")
            if len(city_list) > len(city_weight_list):
                # Extend weights list with the last weight
                last_weight = city_weight_list[-1] if city_weight_list else 1.0
                city_weight_list.extend([last_weight] * (len(city_list) - len(city_weight_list)))
            else:
                # Truncate weights list
                city_weight_list = city_weight_list[:len(city_list)]
                
        # Verify we have at least some data
        if not car_list or not city_list:
            LOGGER.warning("Using fallback data as lists are empty")
            car_list = ["BMW;320i;150;1998", "AUDI;A4;140;1984"]
            car_weight_list = [0.5, 1.0]
            city_list = ["12345;Berlin;13.4050;52.5200", "80331;Munich;11.5820;48.1351"]
            city_weight_list = [0.5, 1.0]
    except Exception as e:
        LOGGER.error(f"Error loading data files: {e}")
        # Use fallback data
        car_list = ["BMW;320i;150;1998", "AUDI;A4;140;1984"]
        car_weight_list = [0.5, 1.0]
        city_list = ["12345;Berlin;13.4050;52.5200", "80331;Munich;11.5820;48.1351"]
        city_weight_list = [0.5, 1.0]

    record_count = 0
    LOGGER.info(f"Generating profiles")
    try:
        for _ in range(random.randint(min_profiles, max_profiles)):
            # Generate a profile
            profile = create_profile()
            # Convert profile to JSON payload
            payload = json.dumps(profile)
    
            # Produce the record to Kafka
            producer.produce(kafka_topic_name, key=str(uuid.uuid4()), value=payload)
            LOGGER.info(f"Produced profile to Kafka")
            record_count += 1

            # Simulate processing delay
            time.sleep(seconds_between_profiles)

    except Exception as e:
        LOGGER.error(f"Error producing profiles to Kafka: {e}")
    finally:
        producer.flush()
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Produced {record_count} profiles to Kafka",
                "profiles_produced": record_count
            })
        }

########################################################################################
#  Load city data from csv file into global array
########################################################################################
def get_cities():
    with open(os.path.join(__location__, 'input_data', 'cities_zip_name_coords.csv'), 'r', encoding='utf-8-sig') as f:
        return f.read().splitlines() 

########################################################################################
#  Load city weights from csv file into global array
########################################################################################
def get_city_weights(): 
    with open(os.path.join(__location__, 'input_data', 'cities_cum_weights.csv'), 'r', encoding='utf-8-sig') as f:
        city_weight_list = f.read().splitlines() 
    return [float(x) for x in city_weight_list]

########################################################################################
#  Load car data from csv file into global array
########################################################################################
def get_cars(): 
    with open(os.path.join(__location__, 'input_data', 'hsn_tsn_car_list.csv'), 'r', encoding='utf-8-sig') as f:
        return f.read().splitlines() 

########################################################################################
#  Load car weights from csv file into global array
########################################################################################
def get_car_weights():
    with open(os.path.join(__location__, 'input_data', 'hsn_tsn_car_cum_weights.csv'), 'r', encoding='utf-8-sig') as f:
        car_weight_list = f.read().splitlines() 
    return [float(x) for x in car_weight_list]

########################################################################################
#  Create synthetic data profile (Customer data, address data, car data, policy data )
########################################################################################
def create_profile():

    profile_rec = {}
    profile = {}

    #Insured Person information
    profile_rec['UserID'] = str(uuid.uuid4())
    profile_rec['Sex'] = random.choices(population=["M", "F"], cum_weights=(493,1000)).pop()

    if profile_rec['Sex'] == "M":
        profile_rec["Prefix"] = "Herr"
        profile_rec["Title"] = fake.prefix_male().replace("Herr", "")
        profile_rec["FirstName"] = fake.first_name_male()
    else:
        profile_rec["Prefix"] = "Frau"
        profile_rec["Title"] = fake.prefix_female().replace("Frau", "")
        profile_rec["FirstName"] = fake.first_name_female()
    profile_rec["LastName"] = fake.last_name()  
    print("NormalizeName")
    profile_rec["NameSearchKey"] =  normalize_name(profile_rec["FirstName"], profile_rec["LastName"])




    actyear = datetime.date.today().year
    ph_birthday = datetime.date(random.randint(actyear-90, actyear-16), random.randint(1,12), random.randint(1,28))
    profile_rec['Birthdate'] =  ph_birthday.isoformat() 

    # Address Information
    print("InjectAddress")
    inject_address(profile_rec)
    
    # Car Information
    print("InjectCar")
    inject_car(profile_rec)

    # Insurance tariff information    
    # Tariff versions in t-shirt sizes and distribution using cumulative weights
    tariffs_list = ["XL", "L", "M", "S", "XS"]
    tariff_cum_weights_list = (10, 30, 70, 90, 100)
    tariff = random.choices(population=tariffs_list, cum_weights=tariff_cum_weights_list).pop()
    inject_tariff_details(profile_rec, tariff)   
 
    # Insurance policy information
    policy_age = max(random.normalvariate(300, 150),1)
    dt_policy_start = date.today() + relativedelta(days = -policy_age)
    profile_rec['CarPolicyState'] = 'Active'
    profile_rec['CarPolicyStartDate'] = dt_policy_start.isoformat()
    profile_rec['CarPolicyTerminationDate'] = ""

    # Who is allowed to drive the car?
    profile_rec['CarFamilyMembersIncluded'] = random.choices(population=["Yes", "No"], cum_weights=(60,100)).pop()
    age_policy_holder = relativedelta(date.today(), ph_birthday ).years
    if profile_rec['CarFamilyMembersIncluded'] == "Yes":
        if age_policy_holder > 16:
            profile_rec['CarAgeYoungestDriver'] = random.randrange(16,age_policy_holder)
        else:
            profile_rec['CarAgeYoungestDriver'] = 16
    else: 
        profile_rec['CarAgeYoungestDriver'] = age_policy_holder 


    # How many claims did the car had in the last months/years?
    profile_rec['CarNrOfClaimsLast24months'] = random.choices(population=["0", "1", "2", "3"], cum_weights=(80,95,99,100)).pop()

    if profile_rec['CarNrOfClaimsLast24months'] == "0":
        profile_rec['CarNoClaimsYears'] = int(round(random.gammavariate(6,1),0))
    else: 
        profile_rec['CarNoClaimsYears'] = random.randrange(0,1)
    
    # Where is the car stored?
    profile_rec['CarMainRepository'] = random.choices(population=["Garage", "Carport", "Street"], cum_weights=(30, 30, 40)).pop()

    # Decide on policystate incl. creation of termination patterns if applicable
    inject_policy_state(profile_rec)
    
    # Create quote
    inject_car_insurance_quote(profile_rec)

    return profile_rec


########################################################################################
#  Helper function to normalize names for index creation
########################################################################################
def normalize_name(firstname, lastname):
    # Mapping dictionary for german "Umlaute"
    d = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e'}

    # normalize firstname
    firstname_normalized = firstname.lower()
    # substitute special chars
    for src, target in d.items():
        firstname_normalized = firstname_normalized.replace(src, target)
    firstname_normalized = re.sub(r'[^a-zA-Z0-9]', '', firstname_normalized)
    # normalize lastname
    lastname_normalized = lastname.lower()
    # substitute special chars
    for src, target in d.items():
        lastname_normalized = lastname_normalized.replace(src, target)
    lastname_normalized = re.sub(r'[^a-zA-Z0-9]', '', lastname_normalized)
    # return normalized name
    return (firstname_normalized + lastname_normalized)


########################################################################################
#  Create patterns for Insurance churns
########################################################################################
def inject_policy_state(profile_rec):
    
    # Create some synthetic termination patterns to include for policy state 
    # ... either through customer or company insurance terminations
    # Seed of churn patterns for later churn prediction training

    pattern_inject_probability = 5 # 5% of profiles include pattern

    # 1. Pattern: luxury car + small tariff + claim patterns => company termination
    if random.randrange(0,100) < pattern_inject_probability: inject_luxury_car_small_tariff_claim_pattern(profile_rec)    
    # 2. Pattern: not luxury car + big tariff + no claim patterns => customer termination
    if random.randrange(0,100) < pattern_inject_probability: inject_no_luxury_car_big_tariff_no_claim_pattern(profile_rec)
    # 3. Pattern: Car age > 10 years + youngest driver < 21 years + city repository + higher premium => customer termination
    if random.randrange(0,100) < pattern_inject_probability: inject_car_age_youngest_driver_city_high_premium_pattern(profile_rec)

########################################################################################
#  Create pattern 1: luxury car + small tariff + claim patterns => company termination
########################################################################################
def inject_luxury_car_small_tariff_claim_pattern(profile_rec):
    if profile_rec['CarPolicyState'] == "Active":
        if random.choices(population=[True, False], cum_weights=(40,100)).pop():
            profile_rec['CarMakeLuxuryFlag'] = True
            profile_rec['CarTariffSize'] = random.choices(population=["S", "XS"], cum_weights=(50,100)).pop()
            profile_rec['CarNrOfClaimsLast24months'] = random.choices(population=["2", "3"], cum_weights=(50,100)).pop()
            profile_rec['CarPolicyState']= random.choices(population=["Company Term", "Active"], cum_weights=(80,100)).pop()

########################################################################################
#  Create pattern 2: not luxury car + big tariff + no claim => customer termination
########################################################################################
def inject_no_luxury_car_big_tariff_no_claim_pattern(profile_rec):
    if profile_rec['CarPolicyState'] == "Active":
        if random.choices(population=[True, False], cum_weights=(40,100)).pop():
            profile_rec['CarMakeLuxuryFlag'] = False
            profile_rec['CarTariffSize'] = random.choices(population=["L", "XL"], cum_weights=(50,100)).pop()
            profile_rec['CarNrOfClaimsLast24months'] = "0"
            profile_rec['CarNoClaimsYears'] = int(round(random.gammavariate(10,1),0))
            profile_rec['CarPolicyState']= random.choices(population=["Customer Term", "Active"], cum_weights=(80,100)).pop()

########################################################################################
#  Create pattern 3: Car age > 10, youngest driver < 21, city repository, high premium => customer termination
########################################################################################
def inject_car_age_youngest_driver_city_high_premium_pattern(profile_rec):
    if profile_rec['CarPolicyState'] == "Active":
        if random.choices(population=[True, False], cum_weights=(40,100)).pop():
            profile_rec['CarAgeYoungestDriver'] = random.randrange(17,21)
            profile_rec['CarMainRepository'] = "Street"
            profile_rec['CarMonthlyPremiumAmount'] = Decimal(random.randrange(80, 120))
            profile_rec['CarAge'] = random.randrange(11,20)
            profile_rec['CarPolicyState']= random.choices(population=["Customer Term", "Active"], cum_weights=(80,100)).pop()

########################################################################################
#  Generate Car Data 
########################################################################################
def inject_car(profile_rec):
    #Insured Object Car information
    car = random.choices(population=car_list, cum_weights=car_weight_list).pop()
    profile_rec['Hsn'] = car.split("|")[0]
    profile_rec['Make'] = car.split("|")[1]
    profile_rec['Tsn'] = car.split("|")[2]
    profile_rec['Model'] = car.split("|")[3]
    profile_rec['Year'] =  min(date.today().year, date.today().year - int(round(random.gammavariate(6,2),0)))    # random.randint(1980, 2022)
    profile_rec['LuxuryCar'] =  get_luxury_flag(profile_rec['Make'])
    
    # Calculate car age based on year
    profile_rec['CarAge'] = date.today().year - profile_rec['Year']

########################################################################################
#  Randomly pick cities from input list and inject data into profile 
########################################################################################  
def inject_address(profile_rec):
    print("getCity")

    city = random.choices(population=city_list, cum_weights=city_weight_list).pop()
    print(city)
    profile_rec['Street'] = fake.street_name()
    profile_rec['HouseNumber'] = fake.building_number()
    profile_rec['ZipCode'] = city.split("|")[0]
    profile_rec['City'] = city.split("|")[1]
    profile_rec['Longitude'] = city.split("|")[2]
    profile_rec['Latitude'] = city.split("|")[3]
    profile_rec['PopulationDensityClass'] = city.split("|")[4]
    profile_rec['PopulationDensityPerSqkm'] = city.split("|")[5]

########################################################################################
#  Simple logic for luxury car indicator
######################################################################################## 
def get_luxury_flag(make):
    luxury_brands = [
        "vw", "bmw", "daimler", "audi", "mercedes", "volvo", "kia", "porsche", 
        "toyota", "tesla", "land rover", "jaguar", "quattro", "ferrari", 
        "maserati", "alpina", "mg rover", "bentley", "rolls-royce", 
        "renault-rvi", "lamborghini"
    ]
    
    for brand in luxury_brands:
        if brand in make.lower():
            return "yes"
    
    return "no"

########################################################################################
#  Generate Insurance tariff details (t-shirt-sized tariff, coverage details)
########################################################################################
def inject_tariff_details(profile_rec, tariff):
    # Tariff level / Size
    profile_rec['CarTariffSize'] = tariff

    if tariff == "XL":
        profile_rec["CarTariffName"] = "Car Insurance XL"
        profile_rec["CarTariffDescription"] = "Best of all coverages with all extras, for maximum peace of mind"
        profile_rec["CarBaseMonthlyPremiumAmount"] = "{:.2f}".format(float(random.randrange(5000, 8000))/100)
        # Cover level
        profile_rec["CarCollisionCover"] = "yes"
        profile_rec["CarTheftCover"] = "yes"
        profile_rec["CarFireCover"] = "yes"
        profile_rec["CarGlassCover"] = "yes"
        profile_rec["CarTransportCover"] = "yes"
        profile_rec["CarVandalismCover"] = "yes"
        # Deductible
        profile_rec["CarDeductible"] = 150
        # Max reimbursement
        profile_rec["CarMaxReimbursementClass"] = "unlimited"
        # Replacement Car
        profile_rec["CarReplacementCar"] = "yes"
        # Parking damage protection
        profile_rec["CarParkingDamageProtection"] = "yes"
        # Weather damage protection
        profile_rec["CarWeatherDamageProtection"] = "yes"
        # Animal bite protection
        profile_rec["CarAnimalBiteProtection"] = "yes"
        # Car Extras Protection
        profile_rec["CarExtrasProtection"] = "yes"
    elif tariff == "L":
        profile_rec["CarTariffName"] = "Car Insurance L"
        profile_rec["CarTariffDescription"] = "Ideal protection including comfort options for your car"
        profile_rec["CarBaseMonthlyPremiumAmount"] = "{:.2f}".format(float(random.randrange(4000, 5000))/100)
        # Cover level
        profile_rec["CarCollisionCover"] = "yes"
        profile_rec["CarTheftCover"] = "yes"
        profile_rec["CarFireCover"] = "yes"
        profile_rec["CarGlassCover"] = "yes"
        profile_rec["CarTransportCover"] = "yes"
        profile_rec["CarVandalismCover"] = "yes"
        # Deductible
        profile_rec["CarDeductible"] = 300
        # Max reimbursement
        profile_rec["CarMaxReimbursementClass"] = "unlimited"
        # Replacement Car
        profile_rec["CarReplacementCar"] = "yes"
        # Parking damage protection
        profile_rec["CarParkingDamageProtection"] = "yes"
        # Weather damage protection
        profile_rec["CarWeatherDamageProtection"] = "yes"
        # Animal bite protection
        profile_rec["CarAnimalBiteProtection"] = "yes"
        # Car Extras Protection
        profile_rec["CarExtrasProtection"] = "no"
    elif tariff == "M":
        profile_rec["CarTariffName"] = "Car Insurance M"
        profile_rec["CarTariffDescription"] = "Well balanced standard protection for your car"
        profile_rec["CarBaseMonthlyPremiumAmount"] = "{:.2f}".format(float(random.randrange(3000, 4000))/100)
        # Cover level
        profile_rec["CarCollisionCover"] = "yes"
        profile_rec["CarTheftCover"] = "yes"
        profile_rec["CarFireCover"] = "yes"
        profile_rec["CarGlassCover"] = "yes"
        profile_rec["CarTransportCover"] = "no"
        profile_rec["CarVandalismCover"] = "no"
        # Deductible
        profile_rec["CarDeductible"] = 500
        # Max reimbursement
        profile_rec["CarMaxReimbursementClass"] = "up to 100k EUR"
        # Replacement Car
        profile_rec["CarReplacementCar"] = "no"
        # Parking damage protection
        profile_rec["CarParkingDamageProtection"] = "yes"
        # Weather damage protection
        profile_rec["CarWeatherDamageProtection"] = "no"
        # Animal bite protection
        profile_rec["CarAnimalBiteProtection"] = "yes"
        # Car Extras Protection
        profile_rec["CarExtrasProtection"] = "no"
    elif tariff == "S":
        profile_rec["CarTariffName"] = "Car Insurance S"
        profile_rec["CarTariffDescription"] = "Economic variant with minimal coverage"
        profile_rec["CarBaseMonthlyPremiumAmount"] = "{:.2f}".format(float(random.randrange(2000, 3000))/100)
        # Cover level
        profile_rec["CarCollisionCover"] = "yes"
        profile_rec["CarTheftCover"] = "yes"
        profile_rec["CarFireCover"] = "yes"
        profile_rec["CarGlassCover"] = "no"
        profile_rec["CarTransportCover"] = "no"
        profile_rec["CarVandalismCover"] = "no"
        # Deductible
        profile_rec["CarDeductible"] = 1000
        # Max reimbursement
        profile_rec["CarMaxReimbursementClass"] = "up to 50k EUR"
        # Replacement Car
        profile_rec["CarReplacementCar"] = "no"
        # Parking damage protection
        profile_rec["CarParkingDamageProtection"] = "no"
        # Weather damage protection
        profile_rec["CarWeatherDamageProtection"] = "no"
        # Animal bite protection
        profile_rec["CarAnimalBiteProtection"] = "no"
        # Car Extras Protection
        profile_rec["CarExtrasProtection"] = "no"
    elif tariff == "XS":
        profile_rec["CarTariffName"] = "Car Insurance XS"
        profile_rec["CarTariffDescription"] = "Absolute basic coverage with high deductible"
        profile_rec["CarBaseMonthlyPremiumAmount"] = "{:.2f}".format(float(random.randrange(1000, 2000))/100)
        # Cover level
        profile_rec["CarCollisionCover"] = "yes"
        profile_rec["CarTheftCover"] = "yes"
        profile_rec["CarFireCover"] = "no"
        profile_rec["CarGlassCover"] = "no"
        profile_rec["CarTransportCover"] = "no"
        profile_rec["CarVandalismCover"] = "no"
        # Deductible
        profile_rec["CarDeductible"] = 1500
        # Max reimbursement
        profile_rec["CarMaxReimbursementClass"] = "up to 25k EUR"
        # Replacement Car
        profile_rec["CarReplacementCar"] = "no"
        # Parking damage protection
        profile_rec["CarParkingDamageProtection"] = "no"
        # Weather damage protection
        profile_rec["CarWeatherDamageProtection"] = "no"
        # Animal bite protection
        profile_rec["CarAnimalBiteProtection"] = "no"
        # Car Extras Protection
        profile_rec["CarExtrasProtection"] = "no"

########################################################################################
#  Calculate individual quote based on customer, car and tariff data
########################################################################################
def inject_car_insurance_quote(profile_rec) :
    
    # Initialize quote with base premium from Tariff 
    profile_rec['CarBaseMonthlyPremiumAmount'] = profile_rec['CarBaseMonthlyPremiumAmount']
    base_premium = Decimal(convert_float_to_decimal(profile_rec['CarBaseMonthlyPremiumAmount']))
    
    # 1. Calculate age factor 
    age_policy_holder = profile_rec['CarAgeYoungestDriver']
    age_factor = Decimal('1.0')

    if age_policy_holder < 18:
        age_factor = Decimal('2.0')
    elif age_policy_holder < 21:
        age_factor = Decimal('1.7')
    elif age_policy_holder < 25:
        age_factor = Decimal('1.4')
    elif age_policy_holder < 29:
        age_factor = Decimal('1.2')
    elif age_policy_holder < 40:
        age_factor = Decimal('1.0')
    elif age_policy_holder < 60:
        age_factor = Decimal('0.9')
    elif age_policy_holder < 70:
        age_factor = Decimal('1.0')
    elif age_policy_holder < 80:
        age_factor = Decimal('1.2')
    else:
        age_factor = Decimal('1.3')
    
    # 2. Calculate car age factor
    car_age = profile_rec['CarAge']
    car_age_factor = Decimal('1.0')
    if car_age < 3:
        car_age_factor = Decimal('1.3')
    elif car_age < 6:
        car_age_factor = Decimal('1.1')
    elif car_age < 10:
        car_age_factor = Decimal('1.0')
    elif car_age < 15:
        car_age_factor = Decimal('1.05')
    elif car_age < 20:
        car_age_factor = Decimal('1.1')
    elif car_age < 30:
        car_age_factor = Decimal('1.2')
    else:
        car_age_factor = Decimal('1.3')

    # 3. Calculate Repository Factor
    repository = profile_rec['CarMainRepository']
    repository_factor = Decimal('1.0')
    if repository == "Garage":
        repository_factor = Decimal('0.8')
    elif repository == "Carport":
        repository_factor = Decimal('0.9')
    else:
        repository_factor = Decimal('1.1')
    
    # 4. Calculate HP category of Car and determine HP factor
    try:
        # Use TSN as a fallback for PS
        if 'Tsn' in profile_rec and 'CarPs' not in profile_rec:
            # Try to convert TSN to a number if possible
            try:
                hp = float(profile_rec['Tsn'])
            except (ValueError, TypeError):
                # If TSN is not numeric, use a default value
                hp = 150  # Default to a mid-range value
        else:
            hp = float(profile_rec['CarPs'])
    except (ValueError, TypeError, KeyError):
        LOGGER.warning(f"Invalid or missing horsepower value. Using default value.")
        hp = 150  # Default to a mid-range value if we can't convert
    
    hp_factor = Decimal('1.0')
    if hp < 74:
        hp_factor = Decimal('0.75')
    elif hp < 110:
        hp_factor = Decimal('0.9')
    elif hp < 147:
        hp_factor = Decimal('1.0')
    elif hp < 184:
        hp_factor = Decimal('1.1')
    elif hp < 221:
        hp_factor = Decimal('1.25')
    elif hp < 258:
        hp_factor = Decimal('1.5')
    elif hp < 295:
        hp_factor = Decimal('2.0')
    elif hp < 368:
        hp_factor = Decimal('2.5')
    else: 
        hp_factor = Decimal('3.0')
    
    # 5. Calculate luxury flag factor
    if profile_rec['LuxuryCar'] == "yes":
        luxury_factor = Decimal('1.5')
    else:
        luxury_factor = Decimal('1.0')

    # 6. Calculate claims factors
    claims = profile_rec['CarNrOfClaimsLast24months']
    claims_factor = Decimal('1.0')
    
    try:
        claims_years = float(profile_rec['CarNoClaimsYears'])
    except (ValueError, TypeError):
        LOGGER.warning(f"Invalid claims years value: {profile_rec['CarNoClaimsYears']}. Using default value.")
        claims_years = 0
        
    claims_years_factor = Decimal('1.0')
    
    if claims == "0":
        claims_factor = Decimal('0.9')
    elif claims == "1":
        claims_factor = Decimal('1.2')
    elif claims == "2":
        claims_factor = Decimal('1.6')
    else:
        claims_factor = Decimal('3.0')

    if claims_years > 0:
        claims_years_factor = Decimal('0.95')
    
    if claims_years > 2:
        claims_years_factor = Decimal('0.9')

    if claims_years > 5:
        claims_years_factor = Decimal('0.85')
    
    if claims_years > 8:
        claims_years_factor = Decimal('0.8')
       
    # Calculate total premium
    profile_rec['CarMonthlyPremiumAmount'] = "%.2f" % (base_premium * age_factor * car_age_factor * repository_factor * hp_factor * luxury_factor * claims_factor * claims_years_factor)

########################################################################################
#  Helper function for JSON serializable string format conversion 
########################################################################################
def convert_float_to_decimal(s): 
    if s is None:
        return s
    try:
        return float(s)
    except (ValueError, TypeError):
        LOGGER.warning(f"Could not convert value to float: {s}")
        return 0.0 