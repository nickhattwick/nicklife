import boto3
import requests
import base64
import json
import datetime
import zoneinfo

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model.dialog import ElicitSlotDirective
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import Response

# Setup the SSM client
ssm = boto3.client('ssm')

def get_parameter(name):
    #Retrieve parameter from SSM Parameter Store
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response['Parameter']['Value']

def update_parameter(name, value):
    """Update parameter in SSM Parameter Store"""
    ssm.put_parameter(Name=name, Value=value, Type='String', Overwrite=True)

def refresh_credentials(client_id, client_secret, refresh_token):
    """Refresh Fitbit token using refresh_token"""
    encoded_credentials = base64.b64encode(f"{client_id}:{client_secret}".encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    response = requests.post('https://api.fitbit.com/oauth2/token', headers=headers, data=data)
    return response.json()

def handle_tokens():
    access_token = get_parameter('FITBIT_ACCESS_TOKEN')
    refresh_token = get_parameter('FITBIT_REFRESH_TOKEN')
    client_id = get_parameter('FITBIT_CLIENT_ID')
    client_secret = get_parameter('FITBIT_CLIENT_SECRET')
    
    # Use access token to make Fitbit API request
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://api.fitbit.com/1/user/-/profile.json', headers=headers)

    if response.status_code == 401:
        refresh_tokens(client_id, client_secret, refresh_token)

    return get_parameter('FITBIT_ACCESS_TOKEN')


def refresh_tokens(client_id, client_secret, refresh_token):
    refreshed_tokens = refresh_credentials(client_id, client_secret, refresh_token)
    update_parameter('FITBIT_ACCESS_TOKEN', refreshed_tokens.get('access_token'))
    update_parameter('FITBIT_REFRESH_TOKEN', refreshed_tokens.get('refresh_token'))


def get_meal_type_id(current_hour):
    if 6 <= current_hour < 11:
        return 1  # Breakfast
    elif 11 <= current_hour < 12:
        return 2  # Morning Snack
    elif 12 <= current_hour < 16:
        return 3  # Lunch
    elif 16 <= current_hour < 18:
        return 4  # Afternoon Snack
    elif 18 <= current_hour < 21:
        return 5  # Dinner
    else:
        return 6  # Anytime

def log_food(access_token, food_id, unit_id, quantity):
    # Headers for the Fitbit API request
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    # Get current date in Eastern time
    eastern = zoneinfo.ZoneInfo('America/New_York')
    now = datetime.datetime.now(eastern)
    today_date = now.strftime('%Y-%m-%d')
    meal_type = get_meal_type_id(now.hour)

    # Construct the data for logging the food
    food_log_data = {
        "foodId": food_id,
        "mealTypeId": meal_type,
        "unitId": unit_id,
        "amount": quantity,
        "date": today_date
    }

    print(food_log_data)

    # Convert the data dictionary to URL parameters
    params = "&".join(f"{key}={value}" for key, value in food_log_data.items())

    # Endpoint for logging the food
    log_endpoint = f"https://api.fitbit.com/1/user/-/foods/log.json?{params}"

    # Make the POST request to log the food
    log_response = requests.post(log_endpoint, headers=headers)
    log_response_json = log_response.json()
    print(log_response_json)

    if log_response.status_code == 201:
        print("Food logged successfully!")
        return {
            'statusCode': 200,
            'body': log_response_json
        }
    else:
        print(f"Failed to log food with status code: {log_response.status_code}")
        print(log_response.text)
        return {
            'statusCode': log_response.status_code,
            'body': log_response_json
        }

def food_logger(handler_input, food_item, session_attributes, user_response=None):
    access_token = handle_tokens()
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    search_endpoint = f"https://api.fitbit.com/1/foods/search.json?query={food_item}"
    search_response = requests.get(search_endpoint, headers=headers)
    
    if search_response.status_code == 200:
        search_results = search_response.json()
        foods = search_results.get('foods')
        
        if foods and len(foods) > 0:
            first_food = foods[0]
            unit_name = first_food.get('defaultUnit').get('name')
            default_serving_size = first_food.get('defaultServingSize')

            unit_name = unit_name if default_serving_size == 1 else first_food.get('defaultUnit').get('plural')

            speak_output = (f"I found {first_food.get('name')}, "
                f"with a default serving size of {default_serving_size} "
                f"{unit_name} "
                f"and {first_food.get('calories')} calories. "
                "Would you like me to log this item?")
            session_attributes['foods'] = foods
            session_attributes['current_index'] = 0
            
            return handler_input.response_builder.speak(speak_output).ask(speak_output).response
        
    else:
        speak_output = "I cant access the food log."
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response

sb = SkillBuilder()

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speak_output = "Welcome to Nick Ate! What did Nick Eat?"
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response


class LogFoodIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogFoodIntent")(handler_input)

    def handle(self, handler_input):
        session_attributes = handler_input.attributes_manager.session_attributes
        food_item = handler_input.request_envelope.request.intent.slots["FoodItem"].value
        user_response = None
        if "UserResponse" in handler_input.request_envelope.request.intent.slots:
            user_response = handler_input.request_envelope.request.intent.slots["UserResponse"].value
        response = food_logger(handler_input, food_item, session_attributes, user_response)
        return response

class ConfirmFoodIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("ConfirmFoodIntent")(handler_input)

    def handle(self, handler_input):
        session_attributes = handler_input.attributes_manager.session_attributes
        if 'foods' in session_attributes:
            access_token = handle_tokens()
            selected_food = session_attributes['foods'][session_attributes['current_index']]
            food_id = selected_food.get('foodId')
            unit_id = selected_food.get('defaultUnit').get('id')
            default_quantity = selected_food.get('defaultServingSize', 1)

            response = log_food(access_token, food_id, unit_id, default_quantity)
            speak_output = f"Wicked, logged that {selected_food['name']} to Fitbit"
        else:
            speak_output = "You have to tell me what you ate first"
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response

class UpdateQuantityIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("UpdateQuantityIntent")(handler_input)

    def handle(self, handler_input):
        session_attributes = handler_input.attributes_manager.session_attributes
        access_token = handle_tokens()
        quantity = handler_input.request_envelope.request.intent.slots["quantity"].value
        selected_food = session_attributes['foods'][session_attributes['current_index']]
        unit_id = selected_food.get('defaultUnit').get('id')

        quantity = float(quantity)

        unit_name = selected_food.get('defaultUnit').get('name') if quantity == 1 else selected_food.get('defaultUnit').get('plural')
        food_id = selected_food.get('foodId')

        response = log_food(access_token, food_id, unit_id, quantity)
        speak_output = f"Wicked, logged {quantity} {unit_name} of {selected_food['name']} to Fitbit"
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response

class SwitchFoodIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("SwitchFoodIntent")(handler_input)

    def handle(self, handler_input):
        session_attributes = handler_input.attributes_manager.session_attributes
        if 'foods' in session_attributes:
            index = session_attributes['current_index'] + 1
            if index < len(session_attributes['foods']):
                next_food = session_attributes['foods'][index]
                unit_name = next_food.get('defaultUnit').get('name')
                default_serving_size = next_food.get('defaultServingSize')
                unit_name = unit_name if default_serving_size == 1 else next_food.get('defaultUnit').get('plural')
                speak_output = (f"How about {next_food.get('name')}, "
                                f"with a default serving size of {default_serving_size} "
                                f"{unit_name} "
                                f"and {next_food.get('calories')} calories. "
                                "Would you like me to log that instead?")
                session_attributes['current_index'] = index
                session_attributes['action'] = 'confirm'
            else:
                speak_output = "I'm out of options. Let's try a different query."
                session_attributes = {}
        
        else:
            speak_output = "Tell me what you ate first"

        return handler_input.response_builder.speak(speak_output).ask(speak_output).response

class StopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "Thanks. Keep me posted on what you eat."
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response

class CancelIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.CancelIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = "Come back when you have more food to tell me about!"
        return handler_input.response_builder.speak(speak_output).set_should_end_session(True).response

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(LogFoodIntentHandler())
sb.add_request_handler(StopIntentHandler())
sb.add_request_handler(CancelIntentHandler())
sb.add_request_handler(ConfirmFoodIntentHandler())
sb.add_request_handler(UpdateQuantityIntentHandler())
sb.add_request_handler(SwitchFoodIntentHandler())

lambda_handler = sb.lambda_handler()