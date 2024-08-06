import os
from flask import Flask, jsonify, request
from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi
from discord_interactions import verify_key_decorator
import requests
from datetime import datetime
import re
import discord
from bs4 import BeautifulSoup

DISCORD_PUBLIC_KEY = "3950e6645d0ef7baa29d168b3487397a0da0b64e028652fa1f858425560578e9"
YEAR_MASTER = "2024"
SEMESTER_MASTER = "fall"

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app)

def search_course(subject, number):
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Determine the current semester
    if current_month < 6:
        semesters = [f"spring {current_year}", f"fall {current_year-1}", f"spring {current_year-1}", f"fall {current_year-2}"]
    else:
        semesters = [f"fall {current_year}", f"spring {current_year}", f"fall {current_year-1}", f"spring {current_year-1}"]
    
    for semester in semesters:
        info_list = make_api_call(subject, number, semester)
        if info_list != "Course not found":
            return info_list
    
    return None

def pull_out_prereqs(input_string):
    result_string = ""
    if input_string is not None:
        result_string = ""
        match = re.search(r'Prerequisite:\s*(.*)', input_string)
        if match:
            result_string = match.group(1)
        else:
            result_string = ""
        if result_string == "":
            result_string = "None"
    else:
        result_string = "None"

    return result_string
def create_course_embed(info_list, subject, number):
    course_explorer_url = f"https://courses.illinois.edu/schedule/{info_list[1]}/{info_list[2].lower()}/{subject}/{number}"
    title = f"{info_list[2]} {info_list[3]}: {info_list[4]}"

    term = f"{info_list[1].capitalize()} {str(info_list[0])}"
    
    embed = discord.Embed(title=title, url=course_explorer_url, description=info_list[5], color=discord.Color.blue())
    embed.add_field(name="Prerequisites", value=pull_out_prereqs(info_list[5]), inline=False)
    embed.add_field(name="Credit Hours", value=info_list[6], inline=False)
    embed.add_field(name="Most Recently Offered", value=term, inline=False)
    
    return embed

def make_api_call(subject, number, semester):
    base_url = "https://uiuc-course-api-production.up.railway.app/search"
    query = f"{subject} {number} {semester}"
    
    response = requests.get(base_url, params={"query": query})

    print(response.json())
    
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data
    
    return "Course not found"


@app.route("/", methods=["POST"])
async def interactions():
    print(f"👉 Request: {request.json}")
    raw_request = request.json
    return interact(raw_request)


@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request):
    if raw_request["type"] == 1:  # PING
        response_data = {"type": 1}  # PONG
    else:
        data = raw_request["data"]
        command_name = data["name"]

        if command_name == "hello":
            message_content = "Hello there!"
        elif command_name == "echo":
            original_message = data["options"][0]["value"]
            message_content = f"Echoing: {original_message}"
        elif command_name == "course":
            course_name = data["options"][0]["value"]
            message_content = handle_course_command(course_name)

        response_data = {
            "type": 4,
            "data": {"content": message_content},
        }

    return jsonify(response_data)



def handle_course_command(course_code):

    course_code = course_code.upper().replace(" ", "")
    subject = ''.join(filter(str.isalpha, course_code))
    number = ''.join(filter(str.isdigit, course_code))

    print(f"Searching for {subject} {number}")
    
    info_list = search_course(subject, number)
    
    if info_list is None:
        return {"type": 4, "data": {"content": "Course not found"}}
    
    embed = create_course_embed(info_list, subject, number)
    return {"type": 4, "data": {"embeds": [embed.to_dict()]}}

def handle_open_command(course_code):
    course_code = course_code.upper().replace(" ", "")
    subject = ''.join(filter(str.isalpha, course_code))
    number = ''.join(filter(str.isdigit, course_code))
    
    url = f"https://courses.illinois.edu/cisapp/explorer/schedule/{YEAR_MASTER}/{SEMESTER_MASTER}/{subject}/{number}.xml"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch course data: {e}")
        return {"type": 4, "data": {"content": "Failed to fetch course data"}}

    soup = BeautifulSoup(response.text, 'xml')
    
    course_title = soup.find('label').text if soup.find('label') else "Unknown"
    description = soup.find('description').text if soup.find('description') else "No description available"
    credit_hours = soup.find('creditHours').text if soup.find('creditHours') else "Unknown"
    
    embed = discord.Embed(
        title=f"{subject} {number}: {course_title}",
        url=f"https://courses.illinois.edu/schedule/{YEAR_MASTER}/{SEMESTER_MASTER.lower()}/{subject}/{number}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Credit Hours", value=credit_hours, inline=False)
    
    sections = soup.find_all('section')
    
    for section in sections:
        section_id = section['id']
        section_name = section.text
        section_url = section['href']
        
        try:
            section_response = requests.get(section_url)
            section_response.raise_for_status()
            section_soup = BeautifulSoup(section_response.text, 'xml')
            
            status_element = section_soup.find('enrollmentStatus')
            status = status_element.text if status_element else "Unknown"
        except requests.RequestException:
            status = "Failed to fetch status"
        
        embed.add_field(name=f"Section {section_name}", value=f"Status: {status}", inline=True)
    
    return {"type": 4, "data": {"embeds": [embed.to_dict()]}}


if __name__ == "__main__":
    app.run(debug=True)
