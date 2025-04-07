from random_user_agent.user_agent import UserAgent
from random_user_agent.params import SoftwareName, OperatingSystem

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


from dotenv import dotenv_values


config = dotenv_values(".env")

service = Service(config["CHROMEDRIVER_PATH"])

sofware_names = [SoftwareName.CHROME.value]
operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value]

user_agent_rotator = UserAgent(
    sofware_names=sofware_names, operating_systems=operating_systems, limit=100
)


def get_webpage_html():

    user_agent = user_agent_rotator.get_random_user_agent()
    options = Options()
    options.add_argument("--headless")  # Run Chrome without UI
    options.add_argument("--no-sandbox")  # disable sandbox for all processes
    options.add_argument("--window-size=1920,1080")  # set window size
    options.add_argument("--disable-gpu")  # disable gpu hardware acceleration
    options.add_argument(f"user-agent={user_agent}")  # add user agent

    browser = webdriver.Chrome(service=service, options=options)

    browser.get("https://jobs.buhlergroup.com/")

    browser.quit()

    return


if __name__ == "__main__":
    get_webpage_html()
