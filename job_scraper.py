import json
from models.orchestrator import Orchestrator


def main():
    """
    routine to scrape all the data
    """
    # load company data
    with open("playground_html.json", "r", encoding="utf-8") as f:
        companies_data = json.load(f)

    scraping_procedure = Orchestrator(companies_data)
    scraping_procedure.scrape()
    scraping_procedure.refine()
    scraping_procedure.finish()


if __name__ == "__main__":
    main()
