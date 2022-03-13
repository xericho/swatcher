import argparse
import time
import selenium
import datetime
import os

import swa
import configuration

DEFAULT_CONFIGURATION_FILE = "swatcher.ini"

class state(object):

    def __init__(self):
        self.errorCount = 0
        self.currentLowestFare = None
        self.blockQuery = False
        self.firstQuery = True
        self.notificationHistory = ''
        self.dailyAlertDate = datetime.datetime.now().date()


class swatcher(object):

    def __init__(self):
        self.state = []
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

    def initializeHistory(self, index):

        tripHistory = os.linesep + "Trip Details:"
        ignoreKeys = ['index', 'description']
        for key in self.config.trips[index].__dict__:
            if(any(x in key for x in ignoreKeys)):
                continue
            tripHistory += os.linesep + "   " + key + ": " + str(self.config.trips[index].__dict__[key])

        if(self.config.historyFileBase):
            try:
                historyFileName = self.config.historyFileBase + "-" + str(index) + ".history"
                with open(historyFileName) as historyFile:
                    for line in historyFile:
                        tripHistory = line + tripHistory
            except IOError as e:
                pass

        return tripHistory


    def appendHistoryFile(self, index, message):
        if(self.config.historyFileBase):
            try:
                historyFileName = self.config.historyFileBase + "-" + str(index) + ".history"
                with open(historyFileName, 'a') as historyFile:
                    historyFile.write(message + os.linesep)
            except IOError as e:
                pass


    def sendNotification(self, index, message):

        if(index is None):
            return

        subject = self.config.trips[index].description + ": " + message
        print(self.now() + ": SENDING NOTIFICATION!!! '" + subject + "'")

        if(not self.state[index].notificationHistory):
            # If in here, this is the first notification, so add details to notification and see if history is enabled
            self.state[index].notificationHistory = self.initializeHistory(index)
            self.appendHistoryFile(index, self.now() + ": Monitoring started")
            self.state[index].notificationHistory = self.now() + ": Monitoring started" + os.linesep + self.state[index].notificationHistory

        shortMessage = self.now() + ": " + message
        self.state[index].notificationHistory = shortMessage + os.linesep + self.state[index].notificationHistory
        self.appendHistoryFile(index, shortMessage)

        if(self.config.notification.type == 'smtp'):
            try:
                    # importing this way keeps people who aren't interested in smtplib from installing it..
                # smtplib = __import__('smtplib')
                # if(self.config.notification.useAuth):
                #     server = smtplib.SMTP(self.config.notification.host, self.config.notification.port)
                #     server.ehlo()
                #     server.starttls()
                #     server.login(self.config.notification.username, self.config.notification.password)
                # else:
                #     server = smtplib.SMTP(self.config.notification.host, self.config.notification.port)

                mailMessage = """From: %s\nTo: %s\nX-Priority: 2\nSubject: %s\n\n""" % (self.config.notification.sender, self.config.notification.recipient, subject)
                mailMessage += self.state[index].notificationHistory

                # server.sendmail(self.config.notification.sender, self.config.notification.recipient, mailMessage)
                print(mailMessage)
                # server.quit()

            except Exception as e:
                print(self.now() + ": UNABLE TO SEND NOTIFICATION DUE TO ERROR - " + str(e))
            return
        elif(self.config.notification.type == 'twilio'):
            try:
                    # importing this way keeps people who aren't interested in Twilio from installing it..
                twilio = __import__('twilio.rest')

                client = twilio.rest.Client(self.config.notification.accountSid, self.config.notification.authToken)
                client.messages.create(to = self.config.notification.recipient, from_ = self.config.notification.sender, body = subject)
            except Exception as e:
                print(self.now() + ": UNABLE TO SEND NOTIFICATION DUE TO ERROR - " + str(e))
            return


    def findLowestFareInSegment(self, trip, segment):

        lowestCurrentFare = None

        specificFlights = []
        if(trip.specificFlights):
            specificFlights = [x.strip() for x in trip.specificFlights.split(',')]

        for flight in segment:

                # If flight is sold-out or otherwise unavailable, no reason to process further
            if(flight['fare'] is None):
                continue

                # Now, see if looking for specificFlights - if this is set, all other rules do not matter...
            if(len(specificFlights) and (flight['flight'] not in specificFlights)):
                continue

            if(trip.maxStops < flight['stops']):
                continue

            if((trip.maxDuration > 0.0) and (trip.maxDuration < flight['duration'])):
                continue

            if(lowestCurrentFare is None):
                lowestCurrentFare = flight['fare']
            elif(flight['fare'] < lowestCurrentFare):
                lowestCurrentFare = flight['fare']

        return lowestCurrentFare

    def processTrip(self, trip, driver):
        if(self.state[trip.index].blockQuery):
            return True

        print(self.now() + ": Querying flight '" + trip.description + "'")

        try:
            segments = swa.scrape(
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
            return False
        except swa.scrapeDatesNotOpen as e:
            if(self.state[trip.index].firstQuery):
                self.sendNotification(trip.index, "Dates do not appear open")
                self.state[trip.index].firstQuery = False
            return True
        except swa.scrapeDatePast as e:
            self.sendNotification(trip.index, "Stopping trip monitoring as date has (or is about to) pass")
            self.state[trip.index].blockQuery = True
            return True
        except swa.scrapeTimeout as e:
                # This could be a few things - internet or SWA website is down.
                # it could also mean my WebDriverWait conditional is incorrect/changed. Don't know
                # what to do about this, so for now, just print to screen and try again at next loop
            print(self.now() + ": Timeout waiting for results, will retry next loop")
            return True
        except Exception as e:
            print(e)
            self.state[trip.index].errorCount += 1
            if(self.state[trip.index].errorCount == 10):
                self.state[trip.index].blockQuery = True
                self.sendNotification(trip.index, "Ceasing queries due to frequent errors")
            return True

            # If here, successfully scraped, so reset errorCount
        self.state[trip.index].errorCount = 0

        lowestFare = None
        priceCount = 0
        for segment in segments:
            lowestSegmentFare = self.findLowestFareInSegment(trip, segment)
            if(lowestSegmentFare is None):
                break
            lowestFare = lowestSegmentFare if lowestFare is None else lowestFare + lowestSegmentFare
            priceCount += 1

        if(((lowestFare is not None) and (trip.maxPrice > 0) and (lowestFare > trip.maxPrice)) or (priceCount != len(segments))):
            lowestFare = None

        if(self.state[trip.index].firstQuery):
            if(lowestFare is None):
                self.sendNotification(trip.index, "Fare that meets criteria is UNAVAILABLE")
            else:
                self.sendNotification(trip.index, "Fare now $" + str(lowestFare))
            self.state[trip.index].currentLowestFare = lowestFare
            self.state[trip.index].firstQuery = False
        elif(self.state[trip.index].currentLowestFare is None):
            if(lowestFare is not None):
                self.sendNotification(trip.index, "Fare now $" + str(lowestFare))
                self.state[trip.index].currentLowestFare = lowestFare
        else:
            if(lowestFare is None):
                self.sendNotification(trip.index, "Fare that meets criteria is UNAVAILABLE")
                self.state[trip.index].currentLowestFare = None
            elif(lowestFare != self.state[trip.index].currentLowestFare):
                self.sendNotification(trip.index, "Fare now $" + str(lowestFare))
                self.state[trip.index].currentLowestFare = lowestFare

        if(self.config.dailyAlerts):
            if(self.state[trip.index].dailyAlertDate != datetime.datetime.now().date()):
                if(lowestFare is None):
                    self.sendNotification(trip.index, "Daily alert fare that meets criteria is UNAVAILABLE")
                else:
                    self.sendNotification(trip.index, "Daily alert fare is $" + str(lowestFare))
                self.state[trip.index].dailyAlertDate = datetime.datetime.now().date()

        return True


    def processTrips(self, driver):
        for trip in self.config.trips:
            if(not self.processTrip(trip, driver)):
                return False

        allBlocked = True
        for state in self.state:
            if(not state.blockQuery):
                allBlocked = False
                break

        if(allBlocked):
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

        self.state = [state() for i in range(len(self.config.trips))]



        if(self.config.browser.type == 'chrome'): # Or Chromium
            options = selenium.webdriver.ChromeOptions()
            # options.add_argument('headless')
            options.add_experimental_option("excludeSwitches", ['enable-automation'])
            options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.87 Safari/537.36")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("log-level=" + str(self.config.browser.logLevel))
            service = selenium.webdriver.chrome.service.Service(executable_path=self.config.browser.binaryLocation)
            driver = selenium.webdriver.Chrome(service=service, options=options)
        elif(self.config.browser.type == 'firefox'): # Or Iceweasel
            options = selenium.webdriver.firefox.options.Options()
            options.binary_location = self.config.browser.binaryLocation
            options.add_argument('--headless')
            driver = selenium.webdriver.Firefox(firefox_options = options)
        else:
            print("Unsupported web browser '" + browser.type + "' specified")
            quit()


        while True:

            if(not self.processTrips(driver)):
                break

            time.sleep(self.config.pollInterval * 60)

        return

if __name__ == "__main__":
    swatcher = swatcher()

    swatcher.main()
