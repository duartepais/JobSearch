"""code to fetch data using a company info dict"""

import argparse
import json

from dotenv import dotenv_values
from models.company import CompanyAPI
from utils import read_json_file


config = dotenv_values(".env")
parser = argparse.ArgumentParser()

parser.add_argument(
    "-c",
    "--company_dict",
    type=json.loads,
    help="company info dict",
    required=True,
)


def update_today_data(company_name: str, jobs_dict: dict, error_list: list):
    """Update the today's data"""

    # read yesterday's and today's data
    today_dict = read_json_file(config["TODAY_FILENAME"], create_if_inexistent=True)
    yesterday_dict = read_json_file(config["YESTERDAY_FILENAME"])

    # deal with eventual empty results
    if jobs_dict:
        today_dict[company_name]["job_listings"] = jobs_dict
    else:
        if company_name in yesterday_dict:

            today_dict[company_name]["job_listings"] = yesterday_dict[company_name][
                "job_listings"
            ]
        else:
            today_dict[company_name]["job_listings"] = jobs_dict

    if len(error_list) > 0:
        today_dict[company_name]["errors"] = error_list

    # save the data
    with open(config["TODAY_FILENAME"], "w", encoding="utf-8") as write_file:
        json.dump(today_dict, write_file, indent=1, default=lambda o: o.to_dict())


def main():
    """
    routine to fetch the company's data from its endpoint
    """

    args = parser.parse_args()

    company = CompanyAPI(args.company_dict)

    company.fetch_results()

    update_today_data(company.name, company.jobs_dict, company.errors)


if __name__ == "__main__":
    main()
