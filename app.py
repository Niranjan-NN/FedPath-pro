import streamlit as st
import hashlib
import requests
import folium
from streamlit_folium import st_folium
import json
from dotenv import load_dotenv
import os
from pymongo import MongoClient

# Load environment variables from the .env file
load_dotenv()

# Validate environment variables for MongoDB
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set!")


# Constants (now retrieved from the .env file)
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")  # Ensure your API keys are in .env
AQICN_API_KEY = os.getenv("AQICN_API_KEY")    # Same for this

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client['traffic_app']  # Replace 'traffic_app' with your database name
users_collection = db['users']  # Collection for user data

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to handle user signup
def signup_user(first_name, last_name, username, password, mobile_number, vehicle_number, vehicle_type):
    try:
        # Check if the username already exists
        if users_collection.find_one({"username": username}):
            st.error("Username already exists. Please choose another.")
            return False

        # Insert new user into MongoDB
        hashed_password = hash_password(password)
        users_collection.insert_one({
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "password": hashed_password,
            "mobile_number": mobile_number,
            "vehicle_number": vehicle_number,
            "vehicle_type": vehicle_type
        })
        return True
    except Exception as e:
        st.error(f"Signup failed: {e}")
        return False

# Function to handle user login
def login_user(username, password):
    try:
        # Hash the input password
        hashed_password = hash_password(password)

        # Query MongoDB for a user with the given username and hashed password
        user = users_collection.find_one({"username": username})

        # Check if user exists and the hashed password matches
        if user and user["password"] == hashed_password:
            return True
        else:
            st.error("Invalid username or password.")
            return False
    except Exception as e:
        st.error(f"Login failed: {e}")
        return False


# Function to get weather details from AQICN API based on city name
def get_weather_details(city):
    if city:
        weather_url = f"http://api.waqi.info/feed/{city}/?token={AQICN_API_KEY}"
        try:
            response = requests.get(weather_url).json()

            # Check if the response is valid and contains data
            if response.get("status") != "error" and isinstance(response.get("data"), dict):
                air_quality_index = response["data"].get("aqi", "N/A")
                weather_city = response["data"].get("city", {}).get("name", "Unknown")
                return air_quality_index, weather_city
            else:
                # Handle cases where the station is unknown or API error
                error_message = response.get("data", "Unknown error")
                st.error(f"Error fetching weather data: {error_message}")
                return "N/A", "City not found"
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching data: {e}")
            return "N/A", "Error fetching data"
    else:
        st.error("City not provided. Please enter a valid city.")
        return "N/A", "City not provided"
    


# Function to geocode location using TomTom API
def geocode_location(location):
    url = f"https://api.tomtom.com/search/2/geocode/{location}.json?key={TOMTOM_API_KEY}"
    response = requests.get(url).json()
    if response.get("results"):
        position = response["results"][0]["position"]
        return position["lat"], position["lon"]
    else:
        st.error(f"Unable to geocode location: {location}")
        return None, None


# Function to calculate route details using TomTom API
def get_route_details(start_lat, start_lon, end_lat, end_lon, vehicle_type, fuel_efficiency):
    route_url = (
        f"https://api.tomtom.com/routing/1/calculateRoute/{start_lat},{start_lon}:{end_lat},{end_lon}/json"
        f"?key={TOMTOM_API_KEY}&computeTravelTimeFor=all"
    )
    route_response = requests.get(route_url).json()
    if "routes" in route_response:
        route = route_response["routes"][0]
        travel_time = route["summary"]["travelTimeInSeconds"] / 60  # Convert to minutes
        route_distance = route["summary"]["lengthInMeters"] / 1000  # Convert to km
        geometry = route["legs"][0]["points"]

        # Emission Estimation
        if vehicle_type == "Gasoline":
            emission_factor = 2.31  # kg CO2/l
        elif vehicle_type == "Diesel":
            emission_factor = 2.68  # kg CO2/l
        else:
            emission_factor = 0  # EV emissions

        emissions = (route_distance / fuel_efficiency) * emission_factor
        return travel_time, route_distance, emissions, geometry
    else:
        st.error("Unable to calculate route. Check your locations!")
        return None, None, None, None

# Streamlit UI
def app():
    st.title("User Login/Signup System")

    # Tabs for Login and Signup
    tab1, tab2 = st.tabs(["Login", "Signup"])

    # Login tab
    with tab1:
        st.subheader("Login")
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            if login_user(login_username, login_password):
                st.session_state.logged_in = True
                st.session_state.username = login_username
                st.success("Login successful!")
            else:
                st.error("Invalid username or password!")

    # Signup tab
    with tab2:
        st.subheader("Signup")
        first_name = st.text_input("First Name")
        last_name = st.text_input("Last Name")
        signup_username = st.text_input("Username", key="signup_username")
        signup_password = st.text_input("Password", type="password", key="signup_password")
        mobile_number = st.text_input("Mobile Number")
        vehicle_number = st.text_input("Vehicle Number")
        vehicle_type = st.selectbox("Vehicle Type", ["BS-1", "BS-2", "BS-3", "BS-4", "BS-5", "BS-6"], key="vehicle_type")
        
        if st.button("Signup"):
            if signup_user(first_name, last_name, signup_username, signup_password, mobile_number, vehicle_number, vehicle_type):
                st.success("Signup successful! You can now log in.")
            else:
                st.error("Signup failed. Try again.")

# Traffic and Weather Application
def traffic_and_weather_app():
    st.title("Real-Time Traffic, Weather, and Route Optimization")
    st.write(f"Welcome, {st.session_state.username}!")

    # (No changes here for traffic, weather, and saved routes)
    # Sidebar Navbar with 3 menu items
    sidebar_option = st.sidebar.selectbox(
        "Menu", ["Traffic & Weather", "Dashboard", "Saved Routes"]
    )

    if sidebar_option == "Traffic & Weather":
        weather_city = st.text_input("Enter city or location for weather details:")
        if weather_city:
            air_quality_index, weather_city_name = get_weather_details(weather_city)
            if air_quality_index != "N/A":
                st.write(f"Air Quality Index for {weather_city_name}: {air_quality_index}")
            else:
                st.write("Unable to fetch weather details. Please try another location.")

        # Traffic inputs
        start_location = st.text_input("Enter starting location:")
        end_location = st.text_input("Enter destination:")
        vehicle_type = st.selectbox("Select vehicle type:", ["Gasoline", "Diesel", "Electric"])
        fuel_efficiency = st.slider("Fuel efficiency (km/l or km/kWh for EV):", 1, 30, 15)

        if start_location and end_location:
            start_lat, start_lon = geocode_location(start_location)
            end_lat, end_lon = geocode_location(end_location)

            if start_lat and end_lat:
                travel_time, route_distance, emissions, geometry = get_route_details(
                    start_lat, start_lon, end_lat, end_lon, vehicle_type, fuel_efficiency
                )

                if travel_time and route_distance:
                    st.write(f"Travel Time: {travel_time:.2f} minutes")
                    st.write(f"Distance: {route_distance:.2f} km")
                    st.write(f"Estimated Emissions: {emissions:.2f} kg CO2")

                    # Map Visualization
                    route_map = folium.Map(location=[(start_lat + end_lat) / 2, (start_lon + end_lon) / 2], zoom_start=12)
                    route_coords = [(point["latitude"], point["longitude"]) for point in geometry]
                    folium.PolyLine(route_coords, color="blue", weight=5).add_to(route_map)
                    st_folium(route_map, width=700, height=500)

                    # Save Route Button
                    if st.button("Save Route"):
                        saved_data = {
                            "weather_city": weather_city,
                            "start_location": start_location,
                            "end_location": end_location,
                            "travel_time": travel_time,
                            "route_distance": route_distance,
                            "emissions": emissions,
                            "route_map": route_map._repr_html_()
                        }

                        # Save the route details to a file (JSON)
                        saved_routes = []
                        try:
                            with open("saved_routes.json", "r") as f:
                                saved_routes = json.load(f)
                        except FileNotFoundError:
                            pass

                        saved_routes.append(saved_data)
                        with open("saved_routes.json", "w") as f:
                            json.dump(saved_routes, f)

                        st.success("Route details saved successfully!")

    elif sidebar_option == "Dashboard":
        st.subheader("User Dashboard")

        # Fetch user details from the database
        try:
            user_details = users_collection.find_one({"username": st.session_state.username})

            if user_details:
                st.write(f"**First Name:** {user_details.get('first_name', 'N/A')}")
                st.write(f"**Last Name:** {user_details.get('last_name', 'N/A')}")
                st.write(f"**Username:** {user_details.get('username', 'N/A')}")
                st.write(f"**Mobile Number:** {user_details.get('mobile_number', 'N/A')}")
                st.write(f"**Vehicle Number:** {user_details.get('vehicle_number', 'N/A')}")
                st.write(f"**Vehicle Type:** {user_details.get('vehicle_type', 'N/A')}")
            else:
                st.warning("No user details found.")
        except Exception as e:
            st.error(f"Error loading user details: {e}")

    elif sidebar_option == "Saved Routes":
        st.write("Saved Routes:")

        # Load and display saved routes
        try:
            with open("saved_routes.json", "r") as f:
                saved_routes = json.load(f)
                for idx, route in enumerate(saved_routes):
                    st.write(f"Route {idx + 1}:")
                    st.write(f"Weather City: {route['weather_city']}")
                    st.write(f"Start Location: {route['start_location']}")
                    st.write(f"End Location: {route['end_location']}")
                    st.write(f"Travel Time: {route['travel_time']:.2f} minutes")
                    st.write(f"Route Distance: {route['route_distance']:.2f} km")
                    st.write(f"Emissions: {route['emissions']:.2f} kg CO2")
                    st.write("---")
        except FileNotFoundError:
            st.write("No saved routes found.")


# Main Streamlit App Logic
def main():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        app()  # Show the login/signup page
    else:
        traffic_and_weather_app()  # Show the traffic and weather app after login

# Run the app
if __name__ == '__main__':
    main()
