"""
Data models for companies' websites and job listings
"""

import time
import traceback

from enum import auto, Enum

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from urllib3.exceptions import ReadTimeoutError

from dotenv import dotenv_values

from utils import find_multiple_tags, find_single_tag

config = dotenv_values(".env")

service = Service(config["CHROMEDRIVER_PATH"])

options = Options()
options.add_argument("--headless")  # Run Chrome in headless mode

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
options.add_argument(f"user-agent={USER_AGENT}")

PAGE_LOADING_TIME = 10


class ResultsLoading(Enum):
    """
    Enumeration for the different kinds of results loading
    """

    PAGINATION = auto()
    SAME_PAGE_LOADING = auto()
    SAME_PAGE_ENDLESS = auto()


class Company:
    """
    Abstraction for the company website and its scraping
    """

    def __init__(self, company_dict):
        self.name = company_dict["name"]
        self.url = company_dict["base_url"]
        self.results_loading = self.get_results_loading_type(company_dict)
        self.job_container_metadata = JobContainerMetadata(
            company_dict["job_container"]
        )
        self.results_dict = {}
        self.errors = []

        match self.results_loading:
            case ResultsLoading.PAGINATION:
                self.next_page_dict = company_dict["next_page"]
                if "start_point" in self.next_page_dict:
                    self.current_stage = self.next_page_dict["start_point"]
            case ResultsLoading.SAME_PAGE_LOADING:
                self.more_button_dict = company_dict["load_more"]

    def get_results_loading_type(self, company_dict):
        """Assess which kind of results loading this website has"""

        if "next_page" in company_dict:
            return ResultsLoading.PAGINATION
        elif "load_more" in company_dict:
            return ResultsLoading.SAME_PAGE_LOADING
        else:
            return ResultsLoading.SAME_PAGE_ENDLESS

    def fetch_results(self):
        """Get all the job results available in a company's website"""

        match self.results_loading:
            case ResultsLoading.PAGINATION:
                job_containers = self.fetch_results_of_pagination()

            case ResultsLoading.SAME_PAGE_LOADING:
                full_page_soup = self.fetch_soup_of_incremental_page()
                if full_page_soup:
                    job_containers = self.extract_results_of_single_page_soup(
                        full_page_soup
                    )
                else:
                    self.errors.append("Error while fetching data from URL")
                    job_containers = []

            case ResultsLoading.SAME_PAGE_ENDLESS:
                driver = webdriver.Chrome(service=service, options=options)

                try:
                    driver.get(self.url)
                    time.sleep(PAGE_LOADING_TIME)
                    soup = BeautifulSoup(driver.page_source, features="html.parser")
                    job_containers = self.extract_results_of_single_page_soup(soup)
                    driver.quit()

                except ReadTimeoutError:
                    self.errors.append("Error while fetching data from URL")
                    driver.quit()
                    job_containers = []

        self.results_dict = self.get_results_dict(job_containers)

        if len(self.results_dict) == 0:
            self.errors.append(
                "Zero results were retrieved. Check this company's website"
            )

    def fetch_results_of_pagination(self):
        """Iterate over pages to get all results"""

        driver = webdriver.Chrome(service=service, options=options)

        job_containers = []
        old_nr_results = 0

        try:
            driver.get(self.url)
            time.sleep(PAGE_LOADING_TIME)
        except ReadTimeoutError:
            self.errors.append("Error while fetching data from URL")
            driver.quit()

            return job_containers

        while True:

            page_soup = BeautifulSoup(driver.page_source, features="html.parser")
            new_containers = self.extract_results_of_single_page_soup(page_soup)

            if len(new_containers) == 0:
                break

            job_containers.extend(new_containers)

            new_nr_results = len(self.get_results_dict(job_containers))

            if new_nr_results == old_nr_results:
                break

            old_nr_results = new_nr_results

            try:
                search_statement = self.get_button_search_statement()

                button = driver.find_element(By.XPATH, search_statement)

                driver.execute_script("arguments[0].click();", button)

            except NoSuchElementException:
                break

        driver.quit()

        return job_containers

    def fetch_soup_of_incremental_page(self):
        """Expand the page until no new content is shown"""

        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.get(self.url)
            time.sleep(PAGE_LOADING_TIME)
        except ReadTimeoutError:
            self.errors.append("Error while fetching data from URL")
            driver.quit()

            return None

        old_nr_results = 0

        while True:
            soup = BeautifulSoup(driver.page_source, features="html.parser")

            results = find_multiple_tags(
                soup,
                self.job_container_metadata.main_tag,
                self.job_container_metadata.main_tag_attrs,
                [
                    self.job_container_metadata.title_tag,
                    self.job_container_metadata.id_tag,
                ],
            )

            new_nr_results = len(results)

            # test if number of results has converged
            if new_nr_results == old_nr_results:
                break
            old_nr_results = new_nr_results

            # try if the button can be clicked

            if "attrs" not in self.more_button_dict:
                cmd_str = f"//button[contains (text(),'{self.more_button_dict['button_name']}')]"

            else:
                cmd_str = f"//{self.more_button_dict['tag']}[@{self.more_button_dict['attrs']['key']}='{self.more_button_dict['attrs']['value']}']"

            try:

                button = driver.find_element(By.XPATH, cmd_str)
                driver.execute_script("arguments[0].click();", button)

                time.sleep(PAGE_LOADING_TIME)

            # catch if the button has disappeared
            except NoSuchElementException:
                break

            # write any exception unnaccounted for in the log file
            except Exception:
                self.errors.append(traceback.format_exc())
                break

        driver.quit()

        return soup

    def extract_results_of_single_page_soup(self, full_page_soup):
        """Extract the job containers from a soup object"""

        job_container_soups = find_multiple_tags(
            full_page_soup,
            self.job_container_metadata.main_tag,
            self.job_container_metadata.main_tag_attrs,
            [self.job_container_metadata.title_tag, self.job_container_metadata.id_tag],
        )

        job_containers = []
        for job_soup in job_container_soups:
            try:
                job_containers.append(
                    JobContainer(self.job_container_metadata, job_soup)
                )
            except (ValueError, AttributeError):
                continue
            except Exception:
                self.errors.append(traceback.format_exc())

        return job_containers

    def get_results_dict(self, job_containers):
        """Select unique jobs from the fetched results"""

        job_containers_dict = {job.id: job.title for job in job_containers}

        return job_containers_dict

    def get_button_search_statement(self):
        """Create the statement to search for, when scanning through pagination"""

        if "start_point" in self.next_page_dict:
            self.current_stage += self.next_page_dict["increment"]
            attr_value = self.next_page_dict["attrs"]["incomplete_value"].format(
                page_nr=self.current_stage
            )
            statement = f"//{self.next_page_dict['tag']}[@{self.next_page_dict['attrs']['key']}='{attr_value}']"

        else:
            statement = f"//{self.next_page_dict['tag']}[@{self.next_page_dict['attrs']['key']}='{self.next_page_dict['attrs']['value']}']"

        return statement


class JobContainerMetadata:
    """
    Abstraction containing the important html tags associated with a job container
    """

    def __init__(self, info_dict):
        self.main_tag = info_dict["tag"]
        self.main_tag_attrs = None if "attrs" not in info_dict else info_dict["attrs"]

        if "title_tag" not in info_dict:
            self.title_tag, self.title_tag_attrs = None, None
        else:
            self.title_tag = info_dict["title_tag"]["tag"]
            self.title_tag_attrs = (
                None
                if "attrs" not in info_dict["title_tag"]
                else info_dict["title_tag"]["attrs"]
            )

        if "id_tag" not in info_dict:
            self.id_tag, self.id_tag_attrs, self.id_tag_attr_location = None, None, None
        else:

            self.id_tag = (
                None if "tag" not in info_dict["id_tag"] else info_dict["id_tag"]["tag"]
            )

            self.id_tag_attrs = (
                None
                if "attrs" not in info_dict["id_tag"]
                else info_dict["id_tag"]["attrs"]
            )

            self.id_tag_attr_location = info_dict["id_tag"]["attr_location"]


class JobContainer:
    """
    Abstraction containing the selected info of a job container
    """

    def __init__(self, container_metadata, container_soup):

        self.metadata = container_metadata
        self.title = self.get_title(container_soup)
        self.id = self.get_id(container_soup)

    def get_title(self, soup):
        """
        Fetch job title from soup object
        Input: container soup object
        Output: processed string with job title
        """

        if self.metadata.title_tag is None:
            title_raw_string = soup.text
        else:
            title_soup = find_single_tag(
                soup, self.metadata.title_tag, self.metadata.title_tag_attrs
            )

            title_raw_string = title_soup.text

        title_processed_string = " ".join(
            title_raw_string.replace("\xa0", " ").splitlines()
        ).strip()

        if not title_processed_string:
            raise ValueError(
                "This soup object has an empty text content for the title attribute"
            )

        return title_processed_string

    def get_id(self, soup):
        """
        Fetch id from soup object, if available
        Input: container soup object
        Output: if available, job id, else, job title
        """

        if self.metadata.id_tag:
            id_soup = find_single_tag(
                soup, self.metadata.id_tag, self.metadata.id_tag_attrs
            )

            id_string = id_soup.attrs[self.metadata.id_tag_attr_location].strip()

        elif self.metadata.id_tag_attr_location:
            id_string = soup.attrs[self.metadata.id_tag_attr_location].strip()

        else:
            id_string = self.title.strip()

        if not id_string:
            raise ValueError(
                "This soup object has an empty text content for the id attribute"
            )

        return id_string

    def to_dict(self):
        """
        Get a representable dict of the job
        """

        return {self.id: self.title}
