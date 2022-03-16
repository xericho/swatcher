import argparse
import time
import selenium
import datetime
import os, json
import pandas as pd

import swa
import configuration

DEFAULT_CONFIGURATION_FILE = "swatcher.ini"

class State(object):

    def __init__(self):
        self.errorCount = 0
        self.currentLowestFare = None
        self.blockQuery = False
        self.notificationHistory = ''
        self.dailyAlertDate = datetime.datetime.now().date()


class swatcher(object):

    def __init__(self):
        self.states = []
        self.config = None

    def now(self):
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def parseArguments(self):

        parser = argparse.ArgumentParser(description = "swatcher.py: Utility to monitor SWA for fare price changes")

        parser.add_argument('-f', '--file',
            dest = 'configurationFile',
            help = "Configuration file to use. If unspecified, will be '" + DEFAULT_CONFIGURATION_FILE + "'",
            default = DEFAULT_CONFIGURATION_FILE)

        args = parser.parse_args()

        return args

    def initializeLogs(self, index):

        tripHistory = os.linesep + "Trip Details:"
        ignoreKeys = ['index', 'description']
        for key in self.config.trips[index].__dict__:
            if any(x in key for x in ignoreKeys):
                continue
            tripHistory += os.linesep + "   " + key + ": " + str(self.config.trips[index].__dict__[key])

        if self.config.historyFileBase:
            try:
                historyFileName = self.config.historyFileBase + "-" + str(index) + ".history"
                with open(historyFileName) as historyFile:
                    for line in historyFile:
                        tripHistory = line + tripHistory
            except IOError as e:
                pass

        return tripHistory

    def appendLogFile(self, index, message):
        if self.config.historyFileBase:
            try:
                historyFileName = self.config.historyFileBase + "-" + str(index) + ".history"
                with open(historyFileName, 'a') as historyFile:
                    historyFile.write(message + os.linesep)
            except IOError as e:
                pass

    def initializeCsvHistory(self, trip):
        trip_name = trip.description.split('/')[-1]
        file_path = os.path.join(self.config.tripsDir, f"{trip_name}.csv")
        if os.path.exists(file_path):
            # File exists so it's already initialized
            return
        os.makedirs(self.config.tripsDir, exist_ok=True)
        columns = ['query_datetime', 'returnOrDepart', 'flight', 'departTime', 'arriveTime', 'duration', 'stops', 'fare', 'fareAnytime', 'fareBusinessSelect']
        pd.DataFrame(columns=columns).to_csv(file_path, index=False)
        with open(os.path.join(self.config.tripsDir, f'{trip_name}_config.json'), 'w') as f:
            json.dump({
                'adultPassengersCount': trip.adultPassengersCount,
                'departureDate': trip.departureDate,
                'departureTimeOfDay': trip.departureTimeOfDay,
                'description': trip.description,
                'destinationAirportCode': trip.destinationAirportCode,
                'maxDuration': trip.maxDuration,
                'maxPrice': trip.maxPrice,
                'maxStops': trip.maxStops,
                'originationAirportCode': trip.originationAirportCode,
                'returnDate': trip.returnDate,
                'returnTimeOfDay': trip.returnTimeOfDay,
                'specificFlights': trip.specificFlights,
                'type': trip.type,
            }, f, indent=2)
    
    def appendCsvHistory(self, trip, flights, depart):
        trip_name = trip.description.split('/')[-1]
        file_path = os.path.join(self.config.tripsDir, f"{trip_name}.csv")
        df = pd.read_csv(file_path)
        df_flights = pd.DataFrame(flights)
        df_flights['returnOrDepart'] = 'depart' if depart else 'return'
        df_flights['query_datetime'] = self.now()
        df = pd.concat([df, df_flights]) 
        df.to_csv(file_path, index=False)
            

    def sendNotification(self, index, message):

        if index is None:
            return

        subject = self.config.trips[index].description + ": " + message
        # print(self.now() + ": SENDING NOTIFICATION!!! '" + subject + "'")
        print(f"{self.now()}: {subject}")

        if not self.states[index].notificationHistory:
            # If in here, this is the first notification, so add details to notification and see if history is enabled
            self.states[index].notificationHistory = self.initializeLogs(index)
            self.appendLogFile(index, self.now() + ": Monitoring started")
            self.states[index].notificationHistory = self.now() + ": Monitoring started" + os.linesep + self.states[index].notificationHistory

        shortMessage = self.now() + ": " + message
        self.states[index].notificationHistory = shortMessage + os.linesep + self.states[index].notificationHistory
        self.appendLogFile(index, shortMessage)

        if self.config.notification.type == 'smtp':
            try:
                    # importing this way keeps people who aren't interested in smtplib from installing it..
                smtplib = __import__('smtplib')
                if self.config.notification.useAuth:
                    server = smtplib.SMTP(self.config.notification.host, self.config.notification.port)
                    server.ehlo()
                    server.starttls()
                    server.login(self.config.notification.username, self.config.notification.password)
                else:
                    server = smtplib.SMTP(self.config.notification.host, self.config.notification.port)

                mailMessage = """From: %s\nTo: %s\nX-Priority: 2\nSubject: %s\n\n""" % (self.config.notification.sender, self.config.notification.recipient, subject)
                mailMessage += self.states[index].notificationHistory

                server.sendmail(self.config.notification.sender, self.config.notification.recipient, mailMessage)
                server.quit()
                print(self.now() + ": SENDING NOTIFICATION!!! '" + subject + "'")

            except Exception as e:
                print(self.now() + ": UNABLE TO SEND NOTIFICATION DUE TO ERROR - " + str(e))
            return
        elif self.config.notification.type == 'twilio':
            try:
                    # importing this way keeps people who aren't interested in Twilio from installing it..
                twilio = __import__('twilio.rest')

                client = twilio.rest.Client(self.config.notification.accountSid, self.config.notification.authToken)
                client.messages.create(to = self.config.notification.recipient, from_ = self.config.notification.sender, body = subject)
                print(self.now() + ": SENDING NOTIFICATION!!! '" + subject + "'")
            except Exception as e:
                print(self.now() + ": UNABLE TO SEND NOTIFICATION DUE TO ERROR - " + str(e))
            return


    def findLowestFare(self, trip):
        """
        Filter for 
            - Specific flight numbers
            - Maximum number of stops
            - Maximum duration of segment
            - Maximum price
        and then check for lowest price.
        """
        trip_name = trip.description.split('/')[-1]
        file_path = os.path.join(self.config.tripsDir, f"{trip_name}.csv")
        df = pd.read_csv(file_path)

        # Now, see if looking for specificFlights - if this is set, all other rules do not matter...
        specificFlights = []
        if trip.specificFlights:
            specificFlights = [x.strip() for x in trip.specificFlights.split(',')]

        # if self.config.dailyAlerts:
        #     if self.states[trip.index].dailyAlertDate != datetime.datetime.now().date():
        #         if lowestFare:
        #             self.sendNotification(trip.index, "Daily alert fare is $" + str(lowestFare))
        #         else:
        #             self.sendNotification(trip.index, "Daily alert fare that meets criteria is UNAVAILABLE")
        #         self.states[trip.index].dailyAlertDate = datetime.datetime.now().date()

    def processTrip(self, trip, driver):
        print(f"{self.now()}: Querying flight for {trip.description}")

        try:
            departFlights, returnFlights = swa.scrape(
                driver = driver,
                originationAirportCode = trip.originationAirportCode,
                destinationAirportCode = trip.destinationAirportCode,
                departureDate = trip.departureDate,
                departureTimeOfDay = trip.departureTimeOfDay,
                returnDate = trip.returnDate,
                returnTimeOfDay = trip.returnTimeOfDay,
                tripType = trip.type,
                adultPassengersCount = trip.adultPassengersCount,
                debug = self.config.debug
            )
        except swa.scrapeValidation as e:
            print(e)
            print("\nValidation errors are not retryable, so swatcher is exiting")
            self.states[trip.index].blockQuery = True
            return
        except swa.scrapeDatesNotOpen as e:
            self.sendNotification(trip.index, "Dates do not appear open / SWA detected Selenium")
            return
        except swa.scrapeDatePast as e:
            self.sendNotification(trip.index, "Stopping trip monitoring as date has (or is about to) pass")
            self.states[trip.index].blockQuery = True
            return
        except swa.scrapeTimeout as e:
            # This could be a few things - internet or SWA website is down.
            # it could also mean my WebDriverWait conditional is incorrect/changed. Don't know
            # what to do about this, so for now, just print to screen and try again at next loop
            print(self.now() + ": Timeout waiting for results, will retry next loop")
            return
        except Exception as e:
            print(e)
            self.states[trip.index].errorCount += 1
            if self.states[trip.index].errorCount == 10:
                self.states[trip.index].blockQuery = True
                self.sendNotification(trip.index, "Ceasing queries due to frequent errors")
            return
        
        # Successfully scraped data
        self.states[trip.index].blockQuery = True

        # Save flight data
        self.initializeCsvHistory(trip)
        self.appendCsvHistory(trip, departFlights, depart=True)
        self.appendCsvHistory(trip, returnFlights, depart=False)

    def processTrips(self, driver):
        for trip in self.config.trips:
            if not self.processTrip(trip, driver):
                return False

        allBlocked = True
        for state in self.states:
            if not state.blockQuery:
                allBlocked = False
                break

        if allBlocked:
            print(self.now() + ": Stopping swatcher as there are no remaining trips to monitor")
            return False

        return True

    def main(self):

        args = self.parseArguments()
        print(self.now() + ": Parsing configuration file '" + args.configurationFile +"'")

        try:
            self.config = configuration.configuration(args.configurationFile)
        except Exception as e:
            print("Error in processing configuration file: " + str(e))
            quit()

        self.states = [State() for i in range(len(self.config.trips))]

        if self.config.browser.type == 'chrome': # Or Chromium
            options = selenium.webdriver.ChromeOptions()
            # options.add_argument('headless')
            options.add_experimental_option("excludeSwitches", ['enable-automation'])
            options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.87 Safari/537.36")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("log-level=" + str(self.config.browser.logLevel))
            service = selenium.webdriver.chrome.service.Service(executable_path=self.config.browser.binaryLocation)
            driver = selenium.webdriver.Chrome(service=service, options=options)
            driver.minimize_window()
        elif self.config.browser.type == 'firefox': # Or Iceweasel
            options = selenium.webdriver.firefox.options.Options()
            options.binary_location = self.config.browser.binaryLocation
            options.add_argument('--headless')
            driver = selenium.webdriver.Firefox(firefox_options = options)
        else:
            print("Unsupported web browser '" + browser.type + "' specified")
            quit()


        # Stops when all queries have been blocked
        while not all([s.blockQuery for s in self.states]):
            for trip in self.config.trips:
                if not self.states[trip.index].blockQuery:
                    self.processTrip(trip, driver)

        print(f"{self.now()}: Completed scrape")

if __name__ == "__main__":
    swatcher = swatcher()
    swatcher.main()
