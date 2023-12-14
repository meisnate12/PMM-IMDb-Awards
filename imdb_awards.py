import os, random, re, sys, time
from datetime import datetime

if sys.version_info[0] != 3 or sys.version_info[1] < 11:
    print("Version Error: Version: %s.%s.%s incompatible please use Python 3.11+" % (sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    sys.exit(0)

try:
    import requests, json
    from lxml import html
    from pmmutils import logging, util
    from pmmutils.args import PMMArgs
    from pmmutils.exceptions import Failed
    from pmmutils.yaml import YAML
    from tmdbapis import TMDbAPIs, TMDbException
except (ModuleNotFoundError, ImportError):
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)

base_url = "https://www.imdb.com"
options = [
    {"arg": "ns", "key": "no-sleep",     "env": "NO_SLEEP",     "type": "bool", "default": False, "help": "Run without random sleep timers between requests."},
    {"arg": "tr", "key": "trace",        "env": "TRACE",        "type": "bool", "default": False, "help": "Run with extra trace logs."},
    {"arg": "lr", "key": "log-requests", "env": "LOG_REQUESTS", "type": "bool", "default": False, "help": "Run with every request logged."}
]
script_name = "IMDb Awards"
base_dir = os.path.dirname(os.path.abspath(__file__))
pmmargs = PMMArgs("meisnate12/PMM-IMDb-Awards", base_dir, options, use_nightly=False)
logger = logging.PMMLogger(script_name, "imdb_awards", os.path.join(base_dir, "logs"), is_trace=pmmargs["trace"], log_requests=pmmargs["log-requests"])
logger.screen_width = 160
logger.header(pmmargs, sub=True)
logger.separator("Validating Options", space=False, border=False)
logger.start()
event_ids = [i for i in YAML(path=os.path.join(base_dir, "event_ids.yml"), create=True)["event_ids"]]
logger.info(f"Event IDs: {event_ids}")
header = {
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"
}

def _request(url, xpath=None):
    sleep_time = 0 if pmmargs["no-sleep"] else random.randint(2, 6)
    logger.info(f"URL: {url}{f' [Sleep: {sleep_time}]' if sleep_time else ''}")
    response = html.fromstring(requests.get(url, headers=header).content)
    if sleep_time:
        time.sleep(sleep_time)
    return response.xpath(xpath) if xpath else response

os.makedirs(os.path.join(base_dir, "events"), exist_ok=True)
for event_id in event_ids:
    event_yaml = YAML(path=os.path.join(base_dir, "events", f"{event_id}.yml"), create=True)
    event_years = _request(f"{base_url}/event/{event_id}", xpath="//div[@class='event-history-widget']//a/text()")
    first = True
    for event_year in event_years:
        if first or str(event_year) not in event_yaml:
            first = False
            event_yaml[str(event_year)] = {}
            for text in _request(f"{base_url}/event/{event_id}/{event_year}", xpath="//div[@class='article']/script/text()")[0].split("\n"):
                if text.strip().startswith("IMDbReactWidgets.NomineesWidget.push"):
                    jsonline = text.strip()
                    obj = json.loads(jsonline[jsonline.find('{'):-3])
                    for award in obj["nomineesWidgetModel"]["eventEditionSummary"]["awards"]:
                        award_name = award["awardName"]
                        if award_name not in event_yaml[str(event_year)]:
                            event_yaml[str(event_year)][award_name] = {}
                        for cat in award["categories"]:
                            cat_name = cat["categoryName"] if cat["categoryName"] else award_name
                            if cat_name not in event_yaml[str(event_year)][award_name]:
                                event_yaml[str(event_year)][award_name][cat_name] = {"nominee": YAML.inline([]), "winner": YAML.inline([])}
                            for nom in cat["nominations"]:
                                imdb_id = next((n["const"] for n in nom["primaryNominees"] + nom["secondaryNominees"] if n["const"].startswith("tt")), None)
                                if imdb_id:
                                    event_yaml[str(event_year)][award_name][cat_name]["nominee"].append(imdb_id)
                                    if nom["isWinner"]:
                                        event_yaml[str(event_year)][award_name][cat_name]["winner"].append(imdb_id)
    event_yaml.yaml.width = 4096
    event_yaml.save()

with open("README.md", "r") as f:
    readme_data = f.readlines()

readme_data[1] = f"Last generated at: {datetime.utcnow().strftime('%B %d, %Y %H:%M')} UTC\n"

with open("README.md", "w") as f:
    f.writelines(readme_data)

logger.separator(f"{script_name} Finished\nTotal Runtime: {logger.runtime()}")




