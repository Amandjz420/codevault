#!/usr/bin/env python3
"""
Test script for Google Gemini API.
Lists all available models and allows testing a specific model interactively.
"""
import os
import sys

# Add the project to path for Django settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codevault.settings')

import django
django.setup()

from django.conf import settings
import google.generativeai as genai


def list_models():
    """List all available Gemini models."""
    print("\n" + "=" * 60)
    print("Available Gemini Models")
    print("=" * 60)
    
    try:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        models = genai.list_models()
        
        gemini_models = []
        for model in models:
            if 'gemini' in model.name.lower():
                gemini_models.append(model)
        
        if not gemini_models:
            print("No Gemini models found!")
            return None
        
        for i, model in enumerate(gemini_models, 1):
            print(f"\n{i}. {model.name}")
            print(f"   Display Name: {model.display_name}")
            print(f"   Description: {model.description[:80] if model.description else 'N/A'}...")
            print(f"   Supported Methods: {', '.join(model.supported_generation_methods)}")
        
        return gemini_models
    except Exception as e:
        print(f"Error listing models: {e}")
        return None


def test_model(model_name: str):
    """Test a specific Gemini model with user input."""
    print("\n" + "=" * 60)
    print(f"Testing Model: {model_name}")
    print("=" * 60)
    
    try:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(model_name)
        
        print("\nModel loaded successfully!")
        print("Enter a prompt to test (or 'quit' to exit):")
        
        while True:
            user_input = input("\nPrompt> ").strip()
            
            if user_input.lower() in ('quit', 'exit', 'q'):
                print("Exiting...")
                break
            
            if not user_input:
                print("Please enter a non-empty prompt.")
                continue
            
            print("\nSending request...")
            try:
                response = model.generate_content(user_input)
                
                print("\n" + "-" * 60)
                print("RESPONSE:")
                print("-" * 60)
                print(response.text)
                print("-" * 60)
                
                # Check for safety ratings if present
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    print(f"\nPrompt Feedback: {response.prompt_feedback}")
                    
            except Exception as e:
                print(f"Error generating response: {e}")
                
    except Exception as e:
        print(f"Error loading model: {e}")
        return False
    
    return True


def main():
    """Main entry point."""
    print("Google Gemini API Test Tool")
    print("=" * 60)
    
    # Check if API key is configured
    if not getattr(settings, 'GOOGLE_API_KEY', None):
        print("Error: GOOGLE_API_KEY not configured in settings!")
        print("Please set it in your .env file or Django settings.")
        sys.exit(1)
    
    print(f"API Key: {'*' * 10}{settings.GOOGLE_API_KEY[-4:]}")
    
    # List available models
    models = list_models()
    
    if not models:
        sys.exit(1)
    
    # Interactive menu
    while True:
        print("\n" + "=" * 60)
        print("Options:")
        print("  [1-{}] - Select model number to test".format(len(models)))
        print("  [r]    - Refresh model list")
        print("  [q]    - Quit")
        print("=" * 60)
        
        choice = input("\nSelect option> ").strip().lower()
        
        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == 'r':
            models = list_models()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                test_model(models[idx].name)
            else:
                print(f"Invalid model number. Choose 1-{len(models)}")
        elif choice.startswith('models/'):
            # Direct model name input
            test_model(choice)
        else:
            print("Invalid option. Please try again.")


if __name__ == '__main__':
    main()
