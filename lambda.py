import os
import json
import boto3
import base64
import requests
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model.dialog import ElicitSlotDirective
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import Response
from token_handler import handle_tokens, get_parameter


ssm = boto3.client('ssm')

class DailySummaryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("DailySummaryIntent")(handler_input)

    def handle(self, handler_input):
        OPENAI_API_KEY      = get_parameter('OPENAI_API_KEY')
        session_attributes = handler_input.attributes_manager.session_attributes

        # Call OpenAI API using requests library
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}'
        }
        data = {
            'model': 'gpt-3.5-turbo-1106',
            'messages': [{'role': 'user', 'content': session_attributes['prompt']}],
            'temperature': 0.7
        }
        
        response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data)
        response_json = response.json()
        print("Response from OpenAI: ", response_json)
        speech_text = response_json['choices'][0]['message']['content']

        handler_input.response_builder.speak(speech_text).set_should_end_session(True)
        return handler_input.response_builder.response


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        session_attributes = handler_input.attributes_manager.session_attributes
        FITBIT_ACCESS_TOKEN = handle_tokens()
        # Query Fitbit API
        headers = {'Authorization': 'Bearer ' + FITBIT_ACCESS_TOKEN}
        sleep_data = requests.get('https://api.fitbit.com/1/user/-/sleep/date/today.json', headers=headers).json()
        food_data = requests.get('https://api.fitbit.com/1/user/-/foods/log/date/today.json', headers=headers).json()
        exercise_data = requests.get('https://api.fitbit.com/1/user/-/activities/date/today.json', headers=headers).json()
        weight_data = requests.get('https://api.fitbit.com/1/user/-/body/log/weight/date/today.json', headers=headers).json()
        profile_data = requests.get('https://api.fitbit.com/1/user/-/profile.json', headers=headers).json()

        print("Sleep Data:", sleep_data)
        print("Food Data:", food_data)
        print("Exercise Data:", exercise_data)
        print("Weight Data:", weight_data)
        print("Profile Data:", profile_data)
        
        # Set age and weight variables
        age = profile_data['user']['age']
        weight = weight_data['weight'][0]['weight'] if 'weight' in weight_data and weight_data['weight'] else 210
        
        food_items = []
        for entry in food_data['foods']:
            food_items.append(f"{entry['loggedFood']['name']} ({entry['loggedFood']['calories']} calories)")
        food_list = ", ".join(food_items)

        prompt = f"Act as a personal trainer / fitness coach and give someone of age {age} and weight {weight}, who ate {food_list} today with a goal of being lean and strong feedback on their day and where to improve. Target 2000 calories, 185 pounds, daily exercise and healthy meals. Be specific in feedback"
        print(prompt)
        session_attributes['prompt'] = prompt
        
        speak_output = "Welcome to NickLife, the hub for all your Nick-related needs!"
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response

class StopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "Thanks for talking, I'll be here for all your Nick-related inquiries"
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response

class CancelIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.CancelIntent")(handler_input)

    def handle(self, handler_input):
        speak_output ="Thanks for talking, I'll be here for all your Nick-related inquiries"
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response


sb = SkillBuilder()
sb.add_request_handler(DailySummaryIntentHandler())
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(StopIntentHandler())
sb.add_request_handler(CancelIntentHandler())

lambda_handler = sb.lambda_handler()

