"""
Data models for comapnies' websites and job listings
"""

import time
import traceback

from enum import auto, Enum

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib3.exceptions import MaxRetryError

from utils import find_multiple_tags, find_single_tag

options = Options()
options.add_argument("--headless")  # Run Chrome in headless mode

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
options.add_argument(f"user-agent={USER_AGENT}")

PAGE_LOADING_TIME = 2


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

        self.error = None

        match self.results_loading:
            case ResultsLoading.PAGINATION:
                self.next_page_dict = company_dict["next_page"]
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
                job_containers = self.extract_results_of_single_page_soup(
                    full_page_soup
                )

            case ResultsLoading.SAME_PAGE_ENDLESS:
                driver = webdriver.Chrome(options=options)
                driver.get(self.url)
                time.sleep(PAGE_LOADING_TIME)

                soup = BeautifulSoup(driver.page_source, features="html.parser")
                job_containers = self.extract_results_of_single_page_soup(soup)

        unique_results = self.get_unique_results(job_containers)

        return unique_results

    def fetch_results_of_pagination(self):
        """Iterate over pages to get all results"""

        driver = webdriver.Chrome(options=options)

        driver.get(self.url)

        job_containers = []
        old_nr_results = 0

        while True:
            time.sleep(PAGE_LOADING_TIME)

            page_soup = BeautifulSoup(driver.page_source, features="html.parser")
            new_containers = self.extract_results_of_single_page_soup(page_soup)

            if len(new_containers) == 0:
                break

            job_containers.extend(new_containers)

            job_containers = self.get_unique_results(job_containers)

            new_nr_results = len(job_containers)

            if new_nr_results == old_nr_results:
                break

            old_nr_results = new_nr_results

            try:
                button = driver.find_element(
                    By.XPATH,
                    f"//{self.next_page_dict["tag"]}[@{self.next_page_dict["attrs"]["key"]}='{self.next_page_dict["attrs"]["value"]}']",
                )

                driver.execute_script("arguments[0].click();", button)

            except NoSuchElementException:
                break

        driver.quit()

        return job_containers

    def fetch_soup_of_incremental_page(self):
        """Expand the page until no new content is shown"""

        driver = webdriver.Chrome(options=options)

        driver.get(self.url)
        time.sleep(PAGE_LOADING_TIME)

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
            try:
                button = driver.find_element(
                    By.XPATH,
                    f"//button[contains (text(),'{self.more_button_dict["button_name"]}')]",
                )
                driver.execute_script("arguments[0].click();", button)

                time.sleep(PAGE_LOADING_TIME)

            # catch if the button has disappeared
            except NoSuchElementException:
                break

            # write any exception unnaccounted for in the log file
            except Exception:
                # TODO write exception in log
                self.error = traceback.format_exc()
                break

        return soup

    def extract_results_of_single_page_soup(self, full_page_soup):
        """Extract the job containers from a soup object"""

        job_container_soups = find_multiple_tags(
            full_page_soup,
            self.job_container_metadata.main_tag,
            self.job_container_metadata.main_tag_attrs,
            [self.job_container_metadata.title_tag, self.job_container_metadata.id_tag],
        )

        job_containers = [
            JobContainer(self.job_container_metadata, job_soup)
            for job_soup in job_container_soups
        ]

        return job_containers

    def get_unique_results(self, job_containers):
        """Select unique jobs from the fetched results"""

        job_containers_dict = {job.id: job for job in job_containers}

        return list(job_containers_dict.values())


class JobContainerMetadata:
    """
    Abstraction containing the important html tags associated with a job container
    """

    def __init__(self, info_dict):
        self.main_tag = info_dict["tag"]
        self.main_tag_attrs = None if "attrs" not in info_dict else info_dict["attrs"]

        self.title_tag = info_dict["title_tag"]["tag"]
        self.title_tag_attrs = (
            None
            if "attrs" not in info_dict["title_tag"]
            else info_dict["title_tag"]["attrs"]
        )

        if "id_tag" not in info_dict:
            self.id_tag, self.id_tag_attrs, self.id_tag_attr_location = None, None, None
        else:
            self.id_tag = info_dict["id_tag"]["tag"]

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

        title_soup = find_single_tag(
            soup, self.metadata.title_tag, self.metadata.title_tag_attrs
        )

        title_raw_string = title_soup.text
        title_processed_string = " ".join(
            title_raw_string.replace("\xa0", " ").splitlines()
        ).strip()

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
            return id_string

        return self.title
