#!/opt/venv/bin/python3

import psycopg2
import requests
import re
import smtplib
import datetime
import bs4
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import collections
import traceback
import colorama
from typing import List, Type
import dateutil.parser

sql_conn = None

# definitions for typehints
ThreadInfo = collections.namedtuple('ThreadInfo', 'subreddit created title url')
CmcInfo = collections.namedtuple('CmcInfo', 'symbol price change_24h change_7d')
CalendarInfo = collections.namedtuple('CalendarInfo', 'coin_name, title date description votes')
EmailFields = collections.namedtuple('EmailFields', 'subject body')


def get_selections() -> yaml:
    with open('selections.yml', 'r') as file1:
        yaml_file = yaml.safe_load(file1.read())
        return yaml_file


def get_creds() -> yaml:
    with open('creds.yml', 'r') as file1:
        yaml_file = yaml.safe_load(file1.read())
        return yaml_file


def sql_handler(opname: str, sql: tuple):
    global sql_conn
    if opname == 'connect':
        sql_conn = psycopg2.connect(host="localhost4", database="daily", user="daily_user", password="daily_pass")
        return True

    cur = sql_conn.cursor()
    debug_sql(cur, sql)
    if opname == 'fetchone':
        cur.execute(*sql)
        result = cur.fetchone()
        return result
    elif opname == 'insertone':
        cur = sql_conn.cursor()
        debug_sql(cur, sql)
        cur.execute(*sql)
        sql_conn.commit()
        return None


def debug_sql(cur, sql):
    debug = False  # set manually
    if debug:
        raw = cur.mogrify(*sql)
        parsed = raw.decode()
        parsed = re.sub('\n|  +', ' ', parsed)
        print(colorama.Fore.YELLOW + f'executing sql: {parsed}' + colorama.Style.RESET_ALL)


def get_reddit_threads():
    subreddits = get_selections()['subreddits']
    thread_list = []
    for subreddit in subreddits:
        url = f'https://www.reddit.com/r/{subreddit}.json'
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        for thread in r.json()['data']['children']:
            thread_info = ThreadInfo(subreddit=subreddit,
                                     created=datetime.datetime.fromtimestamp(int(thread['data']['created'])).strftime(
                                         '%Y-%m-%d'),
                                     title=thread['data']['title'],
                                     url=f"https://reddit.com{thread['data']['permalink']}")
            thread_list.append(thread_info)
    return thread_list


def check_if_new(thread_list: list):
    """check if thread_info exists in db"""
    new_threads = []
    for thread_info in thread_list:
        sql = ("""
            SELECT COUNT(*)
            FROM reddit
            WHERE subreddit=%(subreddit)s 
            AND title=%(title)s
            AND created=%(created)s
            ;""", {
            'subreddit': thread_info.subreddit,
            'title': thread_info.title,
            'created': thread_info.created
        })
        results = sql_handler('fetchone', sql)
        if results[0] == 0:
            save_to_db(thread_info)
            new_threads.append(thread_info)
    return new_threads


def save_to_db(thread_info: ThreadInfo):
    sql = ("""
        INSERT INTO reddit
        VALUES (DEFAULT, %(subreddit)s, %(created)s, %(title)s, %(url)s)
        ;""", {
        'subreddit': thread_info.subreddit,
        'created': thread_info.created,
        'title': thread_info.title,
        'url': thread_info.url
    })
    results = sql_handler('insertone', sql)


def parse_threads_to_html(threads: List[ThreadInfo]) -> str:
    mail_body = '<h1 id="Reddit">Reddit</h1>'
    subreddit = ''
    for thread_info in threads:
        if subreddit != thread_info.subreddit:
            subreddit = thread_info.subreddit
            mail_body += f'<h2>{subreddit}</h2>'
        mail_body += f"<a href=\"{thread_info.url}\">{thread_info.title}</a><br>"
    return mail_body


def parse_calendar_to_html(calendar_info_list: List[CalendarInfo]) -> str:
    mail_body = """
    <h1 id="Calendar">Calendar</h1>
    <style>
    table, th, td {
      border: 1px solid black;
    }
    </style>
    <table>
    <tr>
    <th>Coin name</th>
    <th>Title</th>
    <th>Date</th>
    <th>Description</th>
    <th>Votes</th>
    </tr>
    """
    for index, calendar_info in enumerate(calendar_info_list):
        mail_body += f"<td><a href=\"https://coinmarketcal.com/en/coin/{calendar_info.coin_name}#upcoming\">{calendar_info.coin_name}</a></td>" \
                     f"<td>{calendar_info.title}</td>" \
                     f"<td>{calendar_info.date}</td>" \
                     f"<td>{calendar_info.description}</td>" \
                     f"<td>{calendar_info.votes}</td>" \
                     f"</tr>"
    mail_body += "</table>"
    return mail_body


def send_email(email_body: List[str]):
    toc = 'Quick navigation: <a href="#Reddit">Reddit</a>, <a href="#Price changes">Price changes</a>,' \
          '<a href="#Calendar">Calendar</a>'
    subject = f'news for {datetime.datetime.now().date()}'
    body = toc + ' '.join(email_body)
    email_fields = EmailFields(subject=subject, body=body)
    dispatch_email(email_fields)


def dispatch_email(email_fields: EmailFields):
    email_from = get_creds()['gmail']['user']
    email_pass = get_creds()['gmail']['pass']
    email_to = ['petbot4@gmail.com']

    msg = MIMEMultipart('alternative')
    msg['From'] = email_from
    msg['To'] = ','.join(email_to)
    msg['Subject'] = email_fields.subject

    msg.attach(MIMEText(email_fields.body, 'html'))

    mail_server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    mail_server.login(email_from, email_pass)
    mail_server.sendmail(email_from, email_to, msg.as_string())
    mail_server.close()


def parse_cmc_to_html(tracked_coin_changes: List[CmcInfo]) -> str:
    mail_body = """
    <h1 id="Price changes">Price changes</h1>
    <style>
    table, th, td {
      border: 1px solid black;
    }
    </style>
    <table>
    <tr>
    <th>Symbol</th>
    <th>Price in USD</th>
    <th>24h change in %</th>
    <th>7d change in %</th> 
    </tr>
    """
    for index, cmc_info in enumerate(tracked_coin_changes):
        # add colors
        change_24h = cmc_info.change_24h
        change_7d = cmc_info.change_7d
        if cmc_info.change_24h > 0:
            change_24h = f'<font color="green">{cmc_info.change_24h}</font>'
        elif cmc_info.change_24h < 0:
            change_24h = f'<font color="red">{cmc_info.change_24h}</font>'
        if abs(cmc_info.change_24h) > 10:
            change_24h = f'<b>{change_24h}</b>'
        if cmc_info.change_7d > 0:
            change_7d = f'<font color="green">{cmc_info.change_7d}</font>'
        elif cmc_info.change_7d < 0:
            change_7d = f'<font color="red">{cmc_info.change_7d}</font>'
        if abs(cmc_info.change_7d) > 10:
            change_7d = f'<b>{change_7d}</b>'

        mail_body += f"<tr><td>{cmc_info.symbol}</td>" \
                     f"<td>{cmc_info.price}</td>" \
                     f"<td>{change_24h}</td>" \
                     f"<td>{change_7d}</td>" \
                     f"</tr>"
    mail_body += "</table>"
    return mail_body


def cmc_query(limit=200):
    mode = 'pro'  # set manually
    try:
        connection_info = {
            'pro': {'url': 'https://pro-api.coinmarketcap.com', 'api': get_creds()['cmc']['pro']},
            'sandbox': {'url': 'https://sandbox-api.coinmarketcap.com', 'api': get_creds()['cmc']['sandbox']}
        }
        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'deflate, gzip',
            'X-CMC_PRO_API_KEY': connection_info[mode]['api'],
        }
        url = f"{connection_info[mode]['url']}/v1/cryptocurrency/listings/latest?limit={limit}"
        r = requests.get(url, headers=headers)
        response = r.json()['data']
        return response
    except Exception as e:
        print(e)


def cmc_24h_change(tracked_coins: list):
    raw_cmc_list = cmc_query(400)
    cmc_info_list = []
    for i in raw_cmc_list:
        if i['symbol'] in tracked_coins:
            price = i['quote']['USD']['price']
            if price < 1:
                price = f'{price:.3f}'
            elif price < 10:
                price = f'{price:.2f}'
            else:
                price = f'{price:.0f}'
            cmc_info = CmcInfo(symbol=i['symbol'],
                               price=price,
                               change_24h=float(f"{i['quote']['USD']['percent_change_24h']:.1f}"),
                               change_7d=int(f"{i['quote']['USD']['percent_change_7d']:.0f}")
                               )
            cmc_info_list.append(cmc_info)
    return cmc_info_list


def reddit_sequence() -> str:
    sql_handler('connect', ())
    threads = get_reddit_threads()
    new_threads = check_if_new(threads)
    parsed_threads = parse_threads_to_html(new_threads)
    return parsed_threads


def cmc_sequence() -> str:
    tracked_coins = get_selections()['cmc']
    tracked_coin_changes = cmc_24h_change(tracked_coins)
    cmc_to_html = parse_cmc_to_html(tracked_coin_changes)
    return cmc_to_html


def get_calendar_info() -> List[CalendarInfo]:
    coins = get_selections()['calendar']
    calendar_info_list = []
    for coin in coins:
        url = f"https://coinmarketcal.com/en/coin/{coin}#upcoming"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = r.text

        soup = bs4.BeautifulSoup(response, 'html.parser')

        card = soup.find_all("a", href=True)
        for i in card:
            if i['href'] == '#alertReminder':
                id = i['data-idevent']
                card2 = soup.find("div", id=f"box-{id}")
                description = card2.find("p", class_="card__description").getText()
                votes = card2.find("div", class_="progress__votes").getText()
                votes = votes.split()[0].strip()
                date = dateutil.parser.parse(i['data-date']).date()
                calendar_info = CalendarInfo(coin_name=coin,
                                             title=i['data-title'],
                                             date=date,
                                             description=description,
                                             votes=votes)
                calendar_info_list.append(calendar_info)
    return calendar_info_list


def calendar_sequence():
    calender_info_list = get_calendar_info()
    parse_calendar = parse_calendar_to_html(calender_info_list)
    return parse_calendar


def main():
    try:
        coin_info = cmc_sequence()
        threads = reddit_sequence()
        calendar = calendar_sequence()

        send_email([coin_info, threads, calendar])
    except Exception as e:
        print(f'catch-all exception: \n{e}\n{traceback.format_exc()}')


if __name__ == '__main__':
    colorama.init()
    main()
