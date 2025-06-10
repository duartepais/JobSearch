"""
Collection of functions that help the main file and do not fit the model category
"""

import json
import os
import smtplib

from collections import defaultdict
from email.mime.text import MIMEText


from bs4.element import Tag
from dotenv import dotenv_values

config = dotenv_values(".env")


def find_multiple_tags(
    soup: Tag, tag_name: str, tag_attrs: dict, children_tag_names_list: list
):
    """find the all tags given the different attribute possibilities"""

    if tag_attrs is None:
        first_results = soup.find_all(tag_name)

    elif "value" not in tag_attrs:
        first_results = soup.find_all(tag_name, {tag_attrs["key"]: True})

    else:
        first_results = soup.find_all(tag_name, {tag_attrs["key"]: tag_attrs["value"]})

    tags_it_must_contain = set(
        [child_tag for child_tag in children_tag_names_list if child_tag is not None]
    )

    final_results = [
        result
        for result in first_results
        if all(result.find(child_tag) for child_tag in tags_it_must_contain)
    ]

    return final_results


def find_single_tag(soup: Tag, tag_name: str, tag_attrs: dict):
    """find the specific tag given the different attribute possibilities"""

    if tag_attrs is None:
        return soup.find(tag_name)

    if "value" not in tag_attrs:
        return soup.find(tag_name, {tag_attrs["key"]: True})

    return soup.find(tag_name, {tag_attrs["key"]: tag_attrs["value"]})


def read_json_file(filename: str, create_if_inexistent: bool = False):
    """read a specific file, or create an empty version of it if it does not exist"""

    if create_if_inexistent:
        try:
            file_size = os.path.getsize(filename)
            with open(filename, "r", encoding="utf-8") as read_file:
                if file_size == 0:
                    data_dict = defaultdict(dict)
                else:
                    data_dict = defaultdict(dict, json.load(read_file))

        except FileNotFoundError:
            with open(filename, "w", encoding="utf-8"):
                pass
            data_dict = defaultdict(dict)
    else:
        file_size = os.path.getsize(filename)

        with open(filename, "r", encoding="utf-8") as read_file:
            if file_size == 0:
                data_dict = defaultdict(dict)
            else:
                data_dict = json.load(read_file)

    return data_dict


def send_email(email_html: str, email_date: str):
    """
    Send an email with some date on the subject and some html
    """

    html_message = MIMEText(email_html, "html")
    html_message["Subject"] = f"New jobs - {email_date}"
    html_message["From"] = config["FROM_EMAIL_ADDRESS"]
    html_message["To"] = config["TO_EMAIL_ADDRESS"]

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config["FROM_EMAIL_ADDRESS"], config["EMAIL_PASSWORD"])
        server.sendmail(
            config["FROM_EMAIL_ADDRESS"],
            config["TO_EMAIL_ADDRESS"],
            html_message.as_string(),
        )


def kill_chrome_processes():
    """
    Kill all chrome processes
    """

    os.system("pkill -f chrome")
    os.system("pkill -f chromedriver")
    os.system("pkill -f chromium")
    os.system("pkill -f chromium-browser")


def get_by_path(d: dict, path: str):
    """
    Given a nested dict d, return the value in a specific path
    """

    if isinstance(d, list):
        return d

    keys = path.split(".")
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        elif not key:
            d = d[0]
        else:
            return None
    return d


def clean_string(input_string: str) -> str:
    """
    Given an input string, return it without leading, trailing and double spaces and breaklines
    """

    output_string = " ".join(input_string.replace("\xa0", " ").splitlines()).strip()

    output_string = " ".join(output_string.split())

    return output_string.strip()


def clean_api_response(response: str) -> str:
    """
    Given an API response, return it without the byte order mark (BOM)
    """

    return response.text.replace("\ufeff", "")
