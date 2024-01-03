import json, os, random, sys, time
from datetime import datetime, UTC

if sys.version_info[0] != 3 or sys.version_info[1] < 11:
    print("Version Error: Version: %s.%s.%s incompatible please use Python 3.11+" % (sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    sys.exit(0)

try:
    import requests
    from git import Repo
    from lxml import html
    from pmmutils import logging
    from pmmutils.args import PMMArgs
    from pmmutils.yaml import YAML
except (ModuleNotFoundError, ImportError):
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)

base_url = "https://www.imdb.com"
options = [
    {"arg": "ns", "key": "no-sleep",     "env": "NO_SLEEP",     "type": "bool", "default": False, "help": "Run without random sleep timers between requests."},
    {"arg": "cl", "key": "clean",        "env": "CLEAN",        "type": "bool", "default": False, "help": "Run a completely clean run."},
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
event_ids = [i for i in YAML(path=os.path.join(base_dir, "event_ids.yml"))["event_ids"]]
total_ids = len(event_ids)
os.makedirs(os.path.join(base_dir, "events"), exist_ok=True)
logger.info(f"{total_ids} Event IDs: {event_ids}")
header = {
    "Accept-Language": "en-US,en;q=0.5",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/113.0"
}
valid = YAML(path=os.path.join(base_dir, "event_validation.yml"), create=True, start_empty=pmmargs["clean"])

def _request(url, xpath=None, extra=None):
    sleep_time = 0 if pmmargs["no-sleep"] else random.randint(2, 6)
    logger.info(f"{f'{extra} ' if extra else ''}URL: {url}{f' [Sleep: {sleep_time}]' if sleep_time else ''}")
    response = html.fromstring(requests.get(url, headers=header).content)
    if sleep_time:
        time.sleep(sleep_time)
    return response.xpath(xpath) if xpath else response

for i, event_id in enumerate(event_ids, 1):
    event_yaml = YAML(path=os.path.join(base_dir, "events", f"{event_id}.yml"), create=True, start_empty=pmmargs["clean"])
    event_years = []
    for event_year in _request(f"{base_url}/event/{event_id}", xpath="//div[@class='event-history-widget']//a/@href", extra=f"[Event {i}/{total_ids}]"):
        parts = event_year.split("/")
        event_years.append(f"{parts[3]}{f'-{parts[4]}' if parts[4] != '1' else ''}")
    total_years = len(event_years)
    if event_id not in valid:
        valid[event_id] = {"years": [], "awards": [], "categories": []}
    first = True
    for j, event_year in enumerate(event_years, 1):
        event_year = str(event_year)
        if first or pmmargs["clean"]:
            obj = None
            event_slug = f"{event_year}/1" if "-" not in event_year else event_year.replace("-", "/")
            for text in _request(f"{base_url}/event/{event_id}/{event_slug}/?ref_=ev_eh", xpath="//div[@class='article']/script/text()", extra=f"[Event {i}/{total_ids}] [Year {j}/{total_years}]")[0].split("\n"):
                if text.strip().startswith("IMDbReactWidgets.NomineesWidget.push"):
                    jsonline = text.strip()
                    obj = json.loads(jsonline[jsonline.find('{'):-3])
            if obj is None:
                continue
            event_data = {}
            for award in obj["nomineesWidgetModel"]["eventEditionSummary"]["awards"]:
                award_name = award["awardName"].lower()
                award_data = {}
                for cat in award["categories"]:
                    cat_name = cat["categoryName"].lower() if cat["categoryName"] else award_name
                    nominees = []
                    winners = []
                    for nom in cat["nominations"]:
                        imdb_id = next((n["const"] for n in nom["primaryNominees"] + nom["secondaryNominees"] if n["const"].startswith("tt")), None)
                        if imdb_id:
                            nominees.append(imdb_id)
                            if nom["isWinner"]:
                                winners.append(imdb_id)
                    if nominees or winners:
                        if cat_name not in award_data:
                            award_data[cat_name] = {"nominee": YAML.inline([]), "winner": YAML.inline([])}
                        for n in nominees:
                            if n not in award_data[cat_name]["nominee"]:
                                award_data[cat_name]["nominee"].append(n)
                        for w in winners:
                            if w not in award_data[cat_name]["winner"]:
                                award_data[cat_name]["winner"].append(w)
                        if cat_name not in valid[event_id]["categories"]:
                            valid[event_id]["categories"].append(cat_name)
                if award_data:
                    event_data[award_name] = award_data
                    if award_name not in valid[event_id]["awards"]:
                        valid[event_id]["awards"].append(award_name)
            if event_data:
                first = False
                event_yaml[event_year] = event_data
                if event_year not in valid[event_id]["years"]:
                    valid[event_id]["years"].append(event_year)
    valid[event_id]["awards"].sort()
    valid[event_id]["categories"].sort()
    event_yaml.yaml.width = 4096
    event_yaml.save()

final_events = [e for e in valid]
final_events.sort()
valid.data = {e: valid[e] for e in final_events}
valid.save()

if [item.a_path for item in Repo(path=".").index.diff(None) if item.a_path.endswith(".yml")]:

    with open("README.md", "r") as f:
        readme_data = f.readlines()

    readme_data[1] = f"Last generated at: {datetime.now(UTC).strftime('%B %d, %Y %H:%M')} UTC\n"

    with open("README.md", "w") as f:
        f.writelines(readme_data)

logger.separator(f"{script_name} Finished\nTotal Runtime: {logger.runtime()}")




