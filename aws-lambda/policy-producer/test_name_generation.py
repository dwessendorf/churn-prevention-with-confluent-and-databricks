#!/usr/bin/env python3
"""
Test script to verify name generation across all locales in the policy-producer.
Generates 10 names per locale to ensure name generation and transliteration works properly.
"""

import random
from mimesis import Person
from mimesis.locales import Locale
from mimesis.enums import Gender
from unidecode import unidecode

# Mapping of cultural backgrounds to Mimesis locales
culture_to_locale = {
    "German": Locale.DE,
    "American": Locale.EN,
    "British": Locale.EN_GB,
    "French": Locale.FR,
    "Italian": Locale.IT,
    "Spanish": Locale.ES,
    "Dutch": Locale.NL,
    "Chinese": Locale.ZH,
    "Japanese": Locale.JA,
    "Korean": Locale.KO,
    "Indian": Locale.EN,  # Using English for Indian names
    "Australian": Locale.EN_AU,
    "Canadian": Locale.EN_CA,
    "Irish": Locale.EN_GB,
    "Portuguese": Locale.PT,
    "Russian": Locale.RU,
    "Brazilian": Locale.PT_BR,
    "Mexican": Locale.ES_MX,
    "Turkish": Locale.TR,
    "Nigerian": Locale.EN,
    "South African": Locale.EN_GB,
    "Egyptian": Locale.AR_EG,
    "Scandinavian": Locale.SV,
    "Eastern European": Locale.PL,
    "Middle Eastern": Locale.AR_AE,
    "Southeast Asian": Locale.JA,
    "Latin American": Locale.ES_MX,
    "Caribbean": Locale.ES_MX,
    "Sub-Saharan African": Locale.EN_GB,
    "Pacific Islander": Locale.EN_AU,
    "Indigenous": Locale.EN_CA
}

# Function to ensure all characters in a name are Latin
def ensure_latin_characters(name):
    """Ensures a name only contains Latin characters by transliterating non-Latin characters."""
    return unidecode(name)

def generate_names_for_locale(culture, locale, count=10):
    """Generate sample names for a specific locale."""
    print(f"\n=== {culture} (Locale: {locale}) ===")
    
    try:
        # Create Person instance for this locale
        person = Person(locale)
        
        # Generate names with both genders
        for i in range(count):
            gender = Gender.MALE if i % 2 == 0 else Gender.FEMALE
            first_name = person.first_name(gender=gender)
            last_name = person.last_name()
            
            # Get latinized versions
            latin_first = ensure_latin_characters(first_name)
            latin_last = ensure_latin_characters(last_name)
            
            # Check if transliteration was needed
            transliterated = (first_name != latin_first or last_name != latin_last)
            transliteration_indicator = " (transliterated)" if transliterated else ""
            
            print(f"{i+1}. Original: {first_name} {last_name}")
            if transliterated:
                print(f"   Latin:    {latin_first} {latin_last}{transliteration_indicator}")
            
    except Exception as e:
        print(f"Error generating names for {culture}: {e}")

def main():
    """Generate sample names for all locales."""
    print("===== Testing Name Generation Across All Locales =====")
    
    for culture, locale in culture_to_locale.items():
        try:
            generate_names_for_locale(culture, locale)
        except Exception as e:
            print(f"Failed to process {culture}: {e}")
    
    print("\n===== Name Generation Test Complete =====")

if __name__ == "__main__":
    main() 