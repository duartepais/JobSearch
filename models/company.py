"""
Classes for companies' websites and job listings
"""

import json
import re
import traceback

from abc import ABC
from enum import auto, Enum

from bs4 import BeautifulSoup
from bs4.element import Tag

from dotenv import dotenv_values

from models.api import IterativeAPIInteraction, SingleAPIInteraction
from models.browser import (
    SimplePageInteraction,
    LoadMoreInteraction,
    PaginationInteraction,
)
from utils import find_multiple_tags, find_single_tag, get_by_path, clean_string

config = dotenv_values(".env")


class ResultsLoading(Enum):
    """
    Enumeration for the different kinds of results loading
    """

    PAGINATION = auto()
    LOAD_MORE_SAME_PAGE = auto()
    SIMPLE_SAME_PAGE = auto()


class APIResponseFormat(Enum):
    """
    Enumeration for the different kinds of API responses
    """

    JSON = "json"
    HTML = "html"
    JSON_AND_HTML = "json+html"


class CompanyData(ABC):
    """
    Base blueprint for a company's data
    """

    def __init__(self, company_dict, job_container_metadata):
        self.name = company_dict["name"]
        self.url = company_dict["base_url"]

        self.job_container_metadata = job_container_metadata

        self.jobs_dict = {}

        self.errors = []

    def extract_jobs_from_html(self, html: str):
        """Get the appropriate job info from the raw html"""

        if isinstance(self.job_container_metadata, JSONJobContainerMetadata):
            raise ValueError(
                "For this kind of metadata, you should not be using this method"
            )

        page_soup = BeautifulSoup(html, features="html.parser")

        job_container_soups = find_multiple_tags(
            page_soup,
            self.job_container_metadata.main_tag,
            self.job_container_metadata.main_tag_attrs,
            [self.job_container_metadata.title_tag, self.job_container_metadata.id_tag],
        )

        job_containers = []

        for job_soup in job_container_soups:
            try:
                job_containers.append(
                    HTMLJobContainer(self.job_container_metadata, job_soup)
                )
            except (ValueError, AttributeError):
                continue
            except Exception:
                self.errors.append(traceback.format_exc())

        return job_containers

    def extract_jobs_from_json(self, json_dict: dict):
        """Get the appropriate job info from the retrieved json"""

        if isinstance(self.job_container_metadata, HTMLJobContainerMetadata):
            raise ValueError(
                "For this kind of metadata, you should not be using this method"
            )

        job_containers = []

        jobs_list = get_by_path(json_dict, self.job_container_metadata.jobs_path)

        if isinstance(jobs_list, list):
            for job_dict in jobs_list:
                potential_container = JSONJobContainer(
                    self.job_container_metadata, job_dict
                )
                if potential_container.has_valid_country():

                    job_containers.append(potential_container)

        return job_containers


class CompanyAPI(CompanyData):
    """
    Abstraction for the company's API
    """

    def __init__(self, company_dict: dict):

        self.response_format = APIResponseFormat(company_dict["response"]["type"])
        metadata = self.get_job_container_metadata(company_dict)

        super().__init__(company_dict, metadata)

        self.api_interaction = (
            IterativeAPIInteraction(company_dict)
            if "pagination" in company_dict
            else SingleAPIInteraction(company_dict)
        )

    def get_job_container_metadata(self, company_dict: dict):
        """Retrieve the appropriate metadata for the job container"""

        match self.response_format:
            case APIResponseFormat.JSON:
                metadata = JSONJobContainerMetadata(
                    company_dict["response"]["job_container"]
                )
            case APIResponseFormat.HTML:
                metadata = HTMLJobContainerMetadata(
                    company_dict["response"]["job_container"]
                )

            case APIResponseFormat.JSON_AND_HTML:
                metadata = HTMLJobContainerMetadata(
                    company_dict["response"]["job_container"]
                )
                self.html_loc = company_dict["response"]["html_loc"]

        return metadata

    def fetch_results(self):
        """Fetch the data from the endpoint"""

        job_containers = []

        if isinstance(self.api_interaction, IterativeAPIInteraction):

            job_containers_set = set()
            job_nr_old = len(job_containers_set)

            while True:
                response = self.api_interaction.fetch_response()
                job_containers.extend(self.extract_jobs(response))

                job_containers_set.update(
                    [
                        job.refined_id if hasattr(job, "refined_id") else job.job_id
                        for job in job_containers
                    ]
                )

                job_nr_new = len(job_containers_set)

                if job_nr_new == job_nr_old:
                    break

                self.api_interaction.increase_stage_number()
                job_nr_old = job_nr_new

        else:
            response = self.api_interaction.fetch_response()
            job_containers.extend(self.extract_jobs(response))

        self.jobs_dict = {
            job.refined_id if hasattr(job, "refined_id") else job.job_id: job.title
            for job in job_containers
        }

        if not self.jobs_dict:
            self.errors.append(
                f"No results were retrieved; check the website of {self.name}"
            )

    def extract_jobs(self, response: str):
        """Extract jobs from generic response"""

        match self.response_format:
            case APIResponseFormat.JSON:
                response_dict = json.loads(response)

                return self.extract_jobs_from_json(response_dict)

            case APIResponseFormat.JSON_AND_HTML:
                response_dict = json.loads(response)
                response_html = get_by_path(response_dict, self.html_loc)

                return self.extract_jobs_from_html(response_html)

            case APIResponseFormat.HTML:
                response_html = response

                return self.extract_jobs_from_html(response_html)


class CompanyScrape(CompanyData):
    """
    Abstraction for the company website and its scraping
    """

    def __init__(self, company_dict: dict):

        metadata = HTMLJobContainerMetadata(company_dict["job_container"])
        super().__init__(company_dict, metadata)

        self.results_loading = self.get_results_loading_type(company_dict)

    def get_results_loading_type(self, company_dict: dict) -> ResultsLoading:
        """Assess which kind of results loading this website has"""

        if "next_page" in company_dict:
            self.browser_interaction = PaginationInteraction(
                self.url, company_dict["next_page"], company_dict["job_container"]
            )
            return ResultsLoading.PAGINATION
        elif "load_more" in company_dict:
            self.browser_interaction = LoadMoreInteraction(
                self.url, company_dict["load_more"], company_dict["job_container"]
            )
            return ResultsLoading.LOAD_MORE_SAME_PAGE
        else:
            self.browser_interaction = SimplePageInteraction(self.url)
            return ResultsLoading.SIMPLE_SAME_PAGE

    def scrape_results(self):
        """Get all the job results available in a company's website"""

        try:
            self.browser_interaction.run()
        except Exception as error:
            self.errors.append(" ".join(error.args))
        else:
            match self.results_loading:
                case ResultsLoading.PAGINATION:
                    html_list = self.browser_interaction.html_list
                case (
                    ResultsLoading.LOAD_MORE_SAME_PAGE | ResultsLoading.SIMPLE_SAME_PAGE
                ):
                    html_list = [self.browser_interaction.html]

            job_containers = []

            for html in html_list:
                job_containers.extend(self.extract_jobs_from_html(html))

            ids_set = {job.job_id for job in job_containers}
            refined_ids_set = {job.refined_id for job in job_containers}

            if len(refined_ids_set) != len(ids_set):
                self.errors.append(
                    f"Something wrong with the id refinement of the company {self.name}"
                )

                self.jobs_dict = {job.job_id: job.title for job in job_containers}
            else:
                self.jobs_dict = {job.refined_id: job.title for job in job_containers}

            if not self.jobs_dict:
                self.errors.append(
                    f"No results were retrieved; check the website of {self.name}"
                )


class JSONJobContainerMetadata:
    """
    Abstraction containing the JSON paths associated with a job container
    """

    def __init__(self, info_dict: dict):
        self.jobs_path = info_dict["loc"]
        self.title_path = info_dict["title"]["loc"]
        self.id_path = info_dict["id"]["loc"]

        self.country_path = (
            None if "country" not in info_dict else info_dict["country"]["loc"]
        )
        self.country_target = (
            None
            if "country" not in info_dict
            else info_dict["country"]["correct_value"]
        )


class HTMLJobContainerMetadata:
    """
    Abstraction containing the important html tags associated with a job container
    """

    def __init__(self, info_dict: dict):
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
            self.id_tag, self.id_tag_attrs, self.id_tag_attr_location, self.id_regex = (
                None,
                None,
                None,
                None,
            )
        else:

            self.id_tag = (
                None if "tag" not in info_dict["id_tag"] else info_dict["id_tag"]["tag"]
            )

            self.id_tag_attrs = (
                None
                if "attrs" not in info_dict["id_tag"]
                else info_dict["id_tag"]["attrs"]
            )

            self.id_tag_attr_location = (
                None
                if "attr_location" not in info_dict["id_tag"]
                else info_dict["id_tag"]["attr_location"]
            )

            self.id_regex = (
                None
                if "regex" not in info_dict["id_tag"]
                else info_dict["id_tag"]["regex"]
            )


class JobContainer(ABC):
    """
    Blueprint class for a job container
    """

    def __init__(self, job_id, title):
        self.job_id = job_id
        self.title = title

    def to_dict(self):
        """
        Get a representable dict of the job
        """

        return {self.job_id: self.title}


class JSONJobContainer(JobContainer):
    """
    Abstraction containing the selected info of a JSON job container
    """

    def __init__(
        self, container_metadata: JSONJobContainerMetadata, container_dict: dict
    ):

        self.metadata = container_metadata

        self.title = get_by_path(container_dict, self.metadata.title_path)
        self.job_id = get_by_path(container_dict, self.metadata.id_path)

        self.country = (
            get_by_path(container_dict, self.metadata.country_path).lower()
            if (self.metadata.country_path and self.metadata.country_target)
            else None
        )

        super().__init__(self.job_id, self.title)

    def has_valid_country(self) -> bool:
        """
        check if the country where this job is is valid
        """
        if self.country:
            is_country_valid = (
                self.metadata.country_target.strip().lower() == self.country
            )
            return is_country_valid

        return True


class HTMLJobContainer(JobContainer):
    """
    Abstraction containing the selected info of an html job container
    """

    def __init__(
        self, container_metadata: HTMLJobContainerMetadata, container_soup: Tag
    ):

        self.metadata = container_metadata
        self.title = self.get_title(container_soup)
        self.job_id = self.get_job_id(container_soup)
        self.refined_id = self.get_refined_id()

        super().__init__(self.job_id, self.title)

    def get_title(self, soup: Tag):
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

        title_processed_string = clean_string(title_raw_string)

        if not title_processed_string:
            raise ValueError(
                "This soup object has an empty text content for the title attribute"
            )

        return title_processed_string

    def get_job_id(self, soup: Tag):
        """
        Fetch id from soup object, if available
        Input: container soup object
        Output: if available, job id, else, job title
        """

        if self.metadata.id_tag:

            id_soup = find_single_tag(
                soup, self.metadata.id_tag, self.metadata.id_tag_attrs
            )
            if self.metadata.id_tag_attr_location:
                id_string = id_soup.attrs[self.metadata.id_tag_attr_location].strip()
            else:
                id_string = id_soup.text

        elif self.metadata.id_tag_attr_location:
            id_string = soup.attrs[self.metadata.id_tag_attr_location].strip()

        else:
            id_string = self.title.strip()

        if not id_string:
            raise ValueError(
                "This soup object has an empty text content for the id attribute"
            )

        return id_string

    def get_refined_id(self):
        """
        Fetch the refined id from the raw id value, if available
        Output: if available, refined job id, else, raw job id
        """

        if self.metadata.id_regex:
            return re.search(self.metadata.id_regex, self.job_id).group(1)

        return self.job_id
