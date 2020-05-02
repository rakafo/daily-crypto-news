# Overview
This is a tool for people who want to stay on top of crypto news but don't want to waste their time going about it manually. A single report is sent daily, currently containing:
* new reddit threads for selected communities;
* coinmarketcap.com price movement data for tracked currencies;
* upcoming events for tracked currencies;

Sample report is available in file sample-report.pdf.
Best viewed in thunderbird. Special characters, while not properly shown in sample report, are shown as expected in thunderbird.

# Installation on centos8
* postgresql12 postgresql12-server packages are implied to be installed;
* requires a free API key from coinmarketcap;
* requires a or other email account;
1. python3 -m venv /opt/venv (optional);
2. source /opt/venv/bin/activate (optional);
3. sudo su (optional);
4. dnf install ansible;
5. su - postgres;
6. ansible-playbook postgres.yml;
7. exit;
8. edit creds.yml with personal info;
9. edit selections.yml with communities (optional);
10. crontab -e: 0 8 * * * cd /opt/daily-news && ./main.py;

## sample creds.yml
```yaml
---
cmc:
  pro: XXXXXX-XXX
  sandbox: YYYYYY-YYYYY
  
gmail:
  user: some username@somewhere.com
  pass: some password
```