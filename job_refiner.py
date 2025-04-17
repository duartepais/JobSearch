"""code to update history data and send email"""

import json
import os

from datetime import date

from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader
from utils import read_json_file, send_email

EMAIL_JINJA_TEMPLATE = "email.html.jinja"
JINJA_TEMPLATES = "templates"

env = Environment(loader=FileSystemLoader(JINJA_TEMPLATES))

config = dotenv_values(".env")

keyword_list = config["KEYWORDS"].split(",")

history_dict = read_json_file(config["HISTORY_FILENAME"], create_if_inexistent=True)
today_dict = read_json_file(config["TODAY_FILENAME"], create_if_inexistent=False)
yesterday_dict = read_json_file(
    config["YESTERDAY_FILENAME"], create_if_inexistent=False
)

today = date.today().strftime("%Y-%m-%d")


def email_results(results_dict: dict, errors_dict: dict):
    """
    create the email template and send it by email
    """

    email_template = env.get_template(EMAIL_JINJA_TEMPLATE)
    email_content = email_template.render(
        jobs_dict=results_dict, errors_dict=errors_dict
    )

    send_email(email_content, today)


def refine():
    """
    Update the history data, select the new relevant jobs and email them
    """

    all_new_relevant_jobs_dict = {}
    all_new_jobs_dict = {}
    potential_errors_dict = {}

    # for each company
    for company_name, company_dict in today_dict.items():

        # get new results
        yesterday_job_results = (
            {}
            if company_name not in yesterday_dict
            else yesterday_dict[company_name]["job_listings"]
        )

        new_jobs_dict = {
            job_key: job_title
            for job_key, job_title in company_dict["job_listings"].items()
            if job_key not in yesterday_job_results
        }
        all_new_jobs_dict[company_name] = new_jobs_dict

        # get new relevant results
        new_relevant_jobs = {
            job_key: job_title
            for job_key, job_title in new_jobs_dict.items()
            if any(keyword in job_title.lower() for keyword in keyword_list)
        }

        #
        if len(new_relevant_jobs) > 0:
            all_new_relevant_jobs_dict[company_name] = new_relevant_jobs

        if "errors" in company_dict:
            potential_errors_dict[company_name] = company_dict["errors"]

    update_history_data(all_new_jobs_dict)

    email_results(all_new_relevant_jobs_dict, potential_errors_dict)


def update_history_data(jobs_dict: dict):
    """
    update history dict and file with newest jobs
    """

    # initiate entry for missing companies in history dict
    for company_name, company_dict in jobs_dict.items():

        if company_name not in history_dict:
            history_dict[company_name] = {today: company_dict}
        else:
            history_dict[company_name][today] = company_dict

    # save data
    with open(config["HISTORY_FILENAME"], "w", encoding="utf-8") as write_file:
        json.dump(history_dict, write_file, indent=1, default=lambda o: o.to_dict())


def update_yesterday_data():
    """
    Set today's data as yesterday's and delete today's file
    """

    # write today's data on yesterday's file
    with open(config["YESTERDAY_FILENAME"], "w", encoding="utf-8") as write_file:
        json.dump(today_dict, write_file, indent=1, default=lambda o: o.to_dict())

    # delete today's file
    if os.path.exists(config["TODAY_FILENAME"]):
        os.remove(config["TODAY_FILENAME"])


if __name__ == "__main__":
    refine()
