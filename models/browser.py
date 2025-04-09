"""
Classes for browser interactions
"""

import asyncio

from abc import ABC, abstractmethod

import nodriver as uc

from utils import kill_chrome_processes


PAGE_LOADING_TIME = 10  # in seconds
STARTING_ATTEMPTS_LIMIT = 5


class BrowserInteraction(ABC):
    """Base class for browser interactions"""

    def __init__(self, url: str):
        self.url = url
        self.starting_attempts = 1
        self.driver = None

    def run(self):
        """Run the fetching of the html content"""

        uc.loop().run_until_complete(self.fetch_html())
        kill_chrome_processes()

    async def start_driver(self):
        """Repeatedly attempt to start browser's driver"""
        while True:
            try:
                self.driver = await uc.start(headless=True, sandbox=False)
                break
            except (Exception, AttributeError):
                self.starting_attempts += 1
                if self.starting_attempts >= STARTING_ATTEMPTS_LIMIT:
                    raise Exception("Problem while starting the browser")

    @abstractmethod
    async def fetch_html(self):
        """mandatory class method"""


class LoadMoreInteraction(BrowserInteraction):
    """Interaction where results are loaded on the same page by button click"""

    def __init__(self, url: str, load_more_button_dict: dict, content_tag_dict: dict):
        super().__init__(url=url)
        self.load_more_button_dict = load_more_button_dict
        self.content_tag_dict = content_tag_dict
        self.html = None

    async def fetch_html(self):
        """Fetch the html content of the fully loaded page"""

        await self.start_driver()
        page = await self.driver.get(self.url)

        button_select_statement = f"{self.load_more_button_dict['tag']}[{self.load_more_button_dict['attrs']['key']}='{self.load_more_button_dict['attrs']['value']}']"

        nr_content_tags_old = 0

        while True:

            await asyncio.sleep(PAGE_LOADING_TIME)

            nr_content_tags_new = len(
                await page.query_selector_all(self.content_tag_dict["tag"])
            )

            # find the load more button
            if "button_name" in self.load_more_button_dict:
                more_button = None
                possible_buttons = await page.query_selector_all(
                    button_select_statement
                )
                for possible_button in possible_buttons:
                    if (
                        self.load_more_button_dict["button_name"]
                        in possible_button.text
                    ):
                        more_button = possible_button
                        break
            else:
                more_button = await page.query_selector(button_select_statement)

            # if loading button does not exist or page is not loading new content, break
            if more_button is None or nr_content_tags_new == nr_content_tags_old:
                break
            # else, load more content
            else:
                await more_button.click()
                nr_content_tags_old = nr_content_tags_new

        page_source = await page.get_content()
        self.html = page_source

        await page.close()
        self.driver.stop()

        if not self.html:
            raise Exception("The HTML was not successfully fetched")


class PaginationInteraction(BrowserInteraction):
    """Interaction where results are loaded in a pagination system"""

    def __init__(self, url, pagination_dict: dict, content_tag_dict: dict):
        super().__init__(url)
        self.pagination_dict = pagination_dict
        self.content_tag_dict = content_tag_dict
        self.html_list = []

        if "start_point" in self.pagination_dict:
            self.current_stage = self.pagination_dict["start_point"]

    async def fetch_html(self):
        """Fetch the html content of all pages in the available pagination"""

        await self.start_driver()
        page = await self.driver.get(self.url)

        # get the appropriate select statement for the content of interest
        content_select_statement = self.get_content_select_statement()

        elements_set = set()
        nr_elements_old = 0

        while True:
            await asyncio.sleep(PAGE_LOADING_TIME)

            # see if results have converged
            results = await page.query_selector_all(content_select_statement)
            elements_to_add = [result.text_all for result in results]
            elements_set.update(elements_to_add)
            nr_elements_new = len(elements_set)

            if nr_elements_new == nr_elements_old:
                break

            # save content of html
            nr_elements_old = nr_elements_new
            page_source = await page.get_content()
            self.html_list.append(page_source)

            # find the next page button
            button_select_statement = self.get_button_select_statement()
            next_page_button = await page.query_selector(button_select_statement)

            # see if next page button is available
            if next_page_button is None:
                break

            await next_page_button.click()

        await page.close()
        self.driver.stop()

        if not self.html_list:
            raise Exception("None of the pages' HTML could be fetched")
        for html in self.html_list:
            if not html:
                raise Exception(
                    "The HTML of one of the pages was not successfully fetched"
                )

    def get_button_select_statement(self):
        """Create the statement to search for the next page button"""

        if "start_point" in self.pagination_dict:
            self.current_stage += self.pagination_dict["increment"]
            attr_value = self.pagination_dict["attrs"]["incomplete_value"].format(
                page_nr=self.current_stage
            )
            statement = f"{self.pagination_dict['tag']}[{self.pagination_dict['attrs']['key']}='{attr_value}']"

        else:
            statement = f"{self.pagination_dict['tag']}[{self.pagination_dict['attrs']['key']}='{self.pagination_dict['attrs']['value']}']"

        return statement

    def get_content_select_statement(self):
        """Create the statement to search for the content of interest"""
        if "attrs" in self.content_tag_dict:

            if "value" in self.content_tag_dict["attrs"]:
                content_select_statement = f"{self.content_tag_dict['tag']}[{self.content_tag_dict['attrs']['key']}~='{self.content_tag_dict['attrs']['value']}']"
            else:
                content_select_statement = f"{self.content_tag_dict['tag']}[{self.content_tag_dict['attrs']['key']}]"

        else:
            content_select_statement = self.content_tag_dict["tag"]

        return content_select_statement


class SimplePageInteraction(BrowserInteraction):
    """Interaction where results are already all on the same page"""

    def __init__(self, url: str):
        super().__init__(url)
        self.html = None

    async def fetch_html(self):
        """Fetch the html content of the page"""
        await self.start_driver()

        page = await self.driver.get(self.url)

        await asyncio.sleep(PAGE_LOADING_TIME)

        page_source = await page.get_content()

        self.html = page_source

        await page.close()
        self.driver.stop()

        if not self.html:
            raise Exception("The HTML was not successfully fetched")


# TODO create scrolling to bottom interaction for coherent
