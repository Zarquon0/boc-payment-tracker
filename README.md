# boc-payment-tracker
An email scraper for the purpose of extracting precise data regarding payments from participants on the Brown Outing Club's trips.

# Set Up and Usage
In order to be able to run this payment tracker, you will need two things:
- Access to the brownouting.service@gmail.com account
- A `credentials.json` file
If you do not have either of those things and would like to be able to run this, please contact me and we'll get you set up.

Once you have those, clone this repo and add the `credentials.json` file to the project folder. Then, set up your virtual environment:
```bash
# cd boc-payment-tracker/
python3 -m venv .venv/
source .venv/bin/activate
pip install -r requirements.txt
```
With this set up, run the python script (`python3 payment-tracker.py`). You should see a pop up appear in your browser asking you if you actually trust the software you're running. Click through it accepting everything (what, don't you trust me?). After that, the script should run and produce a read out to your terminal as it does. Upon completion, you should see a new CSV with your results!
