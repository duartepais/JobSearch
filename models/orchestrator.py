"""
Data model for the orchestrator
"""

import json
import os

from datetime import date
from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader

from models.company import Company
from utils import read_json_file, send_email

config = dotenv_values(".env")
keyword_list = config["KEYWORDS"].split(",")

env = Environment(loader=FileSystemLoader(config["JINJA_TEMPLATES"]))


class Orchestrator:
    """
    Abstraction for the scraping orchestrator
    """

    def __init__(self, company_list):
        self.company_list = company_list
        self.today = date.today().strftime("%Y-%m-%d")

        self.company_info_dict = read_json_file(config["COMPANY_INFO_FILENAME"])

        self.history_dict = read_json_file(
            config["HISTORY_FILENAME"], create_if_inexistent=True
        )
        self.today_dict = read_json_file(
            config["TODAY_FILENAME"], create_if_inexistent=True
        )
        self.yesterday_dict = read_json_file(
            config["YESTERDAY_FILENAME"], create_if_inexistent=True
        )

    def scrape(self):
        """
        Start the scraping process by iterating over all companies
        """
        for company_dict in self.company_info_dict["companies"]:
            # skip company if it has already been processed today
            if company_dict["name"] in self.today_dict:
                continue

            company = Company(company_dict)

            company.fetch_results()

            self.update_today_data(company.name, company.jobs_dict, company.errors)

    def refine(self):
        """
        Update the history data and select the new relevant jobs
        """

        new_relevant_results_dict = {}
        potential_errors_dict = {}

        for company_name, company_dict in self.today_dict.items():
            yesterday_job_results = (
                {}
                if company_name not in self.yesterday_dict
                else self.yesterday_dict[company_name]["job_listings"]
            )

            new_results_dict = {
                job_key: job_title
                for job_key, job_title in company_dict["job_listings"].items()
                if job_key not in yesterday_job_results
            }

            self.update_history_data(company_name, new_results_dict)

            new_relevant_results = {
                job_key: job_title
                for job_key, job_title in new_results_dict.items()
                if any(keyword in job_title.lower() for keyword in keyword_list)
            }

            if len(new_relevant_results) > 0:
                new_relevant_results_dict[company_name] = new_relevant_results

            if "errors" in company_dict:
                potential_errors_dict[company_name] = company_dict["errors"]

        self.email_new_results(new_relevant_results_dict, potential_errors_dict)

    def finish(self):
        """
        Set today's data as yesterday's and delete today's file
        """

        # write today's data on yesterday's file
        with open(config["YESTERDAY_FILENAME"], "w", encoding="utf-8") as write_file:
            json.dump(
                self.today_dict, write_file, indent=1, default=lambda o: o.to_dict()
            )

        # delete today's file
        if os.path.exists(config["TODAY_FILENAME"]):
            os.remove(config["TODAY_FILENAME"])

    def update_today_data(self, company_name, jobs_dict, error_list):
        """
        update today dict and file with today's job results
        """
        if jobs_dict:
            self.today_dict[company_name]["job_listings"] = jobs_dict
        else:
            if company_name in self.yesterday_dict:

                self.today_dict[company_name]["job_listings"] = self.yesterday_dict[
                    company_name
                ]["job_listings"]
            else:
                self.today_dict[company_name]["job_listings"] = jobs_dict

        if len(error_list) > 0:
            self.today_dict[company_name]["errors"] = error_list

        with open(config["TODAY_FILENAME"], "w", encoding="utf-8") as write_file:
            json.dump(
                self.today_dict, write_file, indent=1, default=lambda o: o.to_dict()
            )

    def update_history_data(self, company_name, jobs_dict):
        """
        update history dict and file with newest jobs
        """

        if company_name not in self.history_dict:
            self.history_dict[company_name] = {self.today: jobs_dict}
        else:
            self.history_dict[company_name][self.today] = jobs_dict

        with open(config["HISTORY_FILENAME"], "w", encoding="utf-8") as write_file:
            json.dump(
                self.history_dict, write_file, indent=1, default=lambda o: o.to_dict()
            )

    def email_new_results(self, results_dict, errors_dict):
        """
        create the email template and send it by email
        """

        email_template = env.get_template(config["EMAIL_JINJA_TEMPLATE"])
        email_content = email_template.render(
            jobs_dict=results_dict, errors_dict=errors_dict
        )

        send_email(email_content, self.today)
