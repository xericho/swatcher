import time
import requests
import collections
import datetime
import re

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException

URL = "https://www.southwest.com/air/booking/select.html"
URL_TIMEOUT = 20

# Preload a dictionary. These are values that are supported by the SWA REST API, but currently unconfigurable
# Some of these can be omitted, but for completeness, I'm including them with default values.
defaultOptions = {
    'returnAirportCode':'',
    'seniorPassengersCount':'0',
    'fareType':'USD',
    'passengerType':'ADULT',
    'promoCode':'',
    'reset':'true',
    'redirectToVision':'true',
    'int':'HOMEQBOMAIR',
    'leapfrogRequest':'true'
}

class scrapeValidation(Exception):
    pass

class scrapeDatePast(Exception):
    pass

class scrapeTimeout(Exception):
    pass

class scrapeGeneral(Exception):
    pass

class scrapeDatesNotOpen(Exception):
    pass

def validateAirportCode(airportCode):

    if(not airportCode.isalpha()):
        raise scrapeValidation("validateAirportCode: '" + airportCode + "' contains non-alphabetic characters")

    if(len(airportCode) != 3):
        raise scrapeValidation("validateAirportCode: '" + airportCode + "' can only be 3 characters")

    return airportCode.upper() # No necessary, but prefer to have in upper case

def validateTripType(tripType):

    if((tripType != "roundtrip") and (tripType != "oneway")):
        raise scrapeValidation("validateTripType: '" + tripType + "' not valid, must be 'roundtrip' or 'oneway'")

    return tripType

def validateDate(date):

    try:
        testDate = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except Exception as ex:
        raise scrapeValidation("validateDate: '" + date + "' not in the format YYYY-MM-DD or invalid")

    today = datetime.datetime.now().date()

        # The reason for having a <= comparison instead of just a < comparison is that it would
        # be too hard validating date and factoring in time of day, so this way swatcher figures
        # if it is the date of flight, you don't need to scrape anymore
    if(testDate <= today):
        raise scrapeDatePast("validateDate: '" + date + "' invalid - scraping can only be done until day before flight")

    return date

def validateTimeOfDay(timeOfDay):
    validTimes = ['ALL_DAY', 'BEFORE_NOON', 'NOON_TO_SIX', 'AFTER_SIX']

    if(any(x in timeOfDay for x in validTimes)):
        return timeOfDay
    elif(timeOfDay == "anytime"):
        return "ALL_DAY"
    elif(timeOfDay == "morning"):
        return "BEFORE_NOON"
    elif(timeOfDay == "afternoon"):
        return "NOON_TO_SIX"
    elif(timeOfDay == "evening"):
        return "AFTER_SIX"
    else:
        raise scrapeValidation("validateTimeOfDay: '" + timeOfDay + "' invalid")

def validatePassengersCount(passengersCount):
    if( 1 <= passengersCount <= 8):
        return passengersCount
    else:
        raise scrapeValidation("validatePassengersCount: '" + passengersCount + "' must be 1 through 8")

def scrapeFare(element, className):

    fare = element.find_element(by=By.CLASS_NAME, value=className).text
    if(("Unavailable" in fare) or ("Sold out" in fare)):
        return None
    else:
        return int(fare.split("$")[1].split()[0])

def scrapeFlights(flight):

    flightDetails = {}

    flightDetails['flight'] = WebDriverWait(flight, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "flight-numbers--flight-number"))) \
        .text.replace(' ','').replace('#', '')

    flightDetails['return'] = flight.find_element(by=By.XPATH, value="//div[@data-test='select-detail--origination-time']").text
    # Text here can contain "Next Day", so just take time portion
    flightDetails['destination'] = flight.find_element(by=By.XPATH, value="//div[@data-test='select-detail--destination-time']").text

    durationList = WebDriverWait(flight, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "select-detail--flight-duration"))).text.split()
    # For flight duration, just round to 2 decimal places - that should be more than enough
    flightDetails['duration'] = round(float(durationList[0].split("h")[0]) +  ((float(durationList[1].split("m")[0])/60.0) + .001), 2)

    # For flights which are non-stop, SWA doesn't display data after the duration
    flightStops = flight.find_element(by=By.CLASS_NAME, value="flight-stops-badge").text
    flightDetails['stops'] = 0 if flightStops == 'Nonstop' else int(flightStops.split(' ')[0])

    # fare-button_primary-yellow == wannaGetAway
    # fare-button_secondary-light-blue == anytime
    # fare-button_primary-blue == businessSelect
    flightDetails['fare'] = scrapeFare(flight, "fare-button_primary-yellow")
    flightDetails['fareAnytime'] = scrapeFare(flight, "fare-button_secondary-light-blue")
    flightDetails['fareBusinessSelect'] = scrapeFare(flight, "fare-button_fare-type-color")

    return flightDetails

def scrape(
        driver,
        originationAirportCode, # 3 letter airport code (eg: MDW - for Midway, Chicago, Illinois)
        destinationAirportCode, # 3 letter airport code (eg: MCO - for Orlando, Florida)
        departureDate, # Flight departure date in YYYY-MM-DD format
        returnDate, # Flight return date in YYYY-MM-DD format (for roundtrip, otherwise ignored)
        tripType = 'roundtrip', # Can be either 'roundtrip' or 'oneway'
        departureTimeOfDay = 'ALL_DAY', # Can be either 'ALL_DAY', 'BEFORE_NOON', 'NOON_TO_SIX', or 'AFTER_SIX' (CASE SENSITIVE)
        returnTimeOfDay = 'ALL_DAY', # Can be either 'ALL_DAY', 'BEFORE_NOON', 'NOON_TO_SIX', or 'AFTER_SIX' (CASE SENSITIVE)
        adultPassengersCount = 1, # Can be a value of between 1 and 8
        debug = False
    ):

    payload = defaultOptions

    # Validate the parameters to ensure nothing is blatently erroneous then load into map
    payload['originationAirportCode'] = validateAirportCode(originationAirportCode)
    payload['destinationAirportCode'] = validateAirportCode(destinationAirportCode)
    payload['tripType'] = validateTripType(tripType)
    payload['departureDate'] = validateDate(departureDate)
    payload['departureTimeOfDay'] = validateTimeOfDay(departureTimeOfDay)
    payload['adultPassengersCount'] = validatePassengersCount(adultPassengersCount)

    if (tripType == 'roundtrip'):
        payload['returnDate'] = validateDate(returnDate)
        payload['returnTimeOfDay'] = validateTimeOfDay(returnTimeOfDay)
    else:
        payload['returnDate'] = '' # SWA REST requires presence of this parameter, even on a 'oneway'

    query =  '&'.join(['%s=%s' % (key, value) for (key, value) in payload.items()])

    fullUrl = URL + '?' + query
    # print(fullUrl)
    driver.get(fullUrl)

    waitCSS = ".page-error--list, .trip--form-container, "
    waitCSS += "#air-booking-product-1" if tripType == 'roundtrip' else "#air-booking-product-0"

    try:
        element = WebDriverWait(driver, URL_TIMEOUT).until(EC.element_to_be_clickable((By.CSS_SELECTOR, waitCSS)))
        # driver.implicitly_wait(10)

    except TimeoutException:
        raise scrapeTimeout("scrape: Timeout occurred after " + str(URL_TIMEOUT) + " seconds waiting for web result")
    except Exception as ex:
        message = "An {0} exception occurred:\n{1!r}".format(type(ex).__name__, ex)
        raise scrapeGeneral("scrape: General exception occurred - " + message)
    finally:
        if debug:
            open("dump-" + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + ".html", "w").write(u''.join((driver.page_source)).encode('utf-8').strip())

    if("page-error--list" in element.get_attribute("class")):
            # In the past (Until 2018-05-26) SWA returned a special class identifier (error-no-routes-exist) to more
            # correctly identify the reason for the failure, and I used this to tell that routes haven't opened. Now
            # that is not possible and my old validation tests started failing, so I'm just using the more generic
            # method of just looking for a class=page-error--list to identify this, as it isn't easy to get
            # this tag to come up, so I'm assuming that dates haven't opened. Will need to think of a better way
            # for this...
        raise scrapeDatesNotOpen("")
    elif("trip--form-container" in element.get_attribute("class")):
            # If in here, the browser is asking to re-enter flight information, meaning that
            # parameters supplied are most likely bad
        raise scrapeValidation("scrape: SWA Website reported what appears to be errors with parameters")

    # If here, we should have results, so  parse out...
    priceMatrixes = driver.find_elements(by=By.CLASS_NAME, value="air-booking-select-price-matrix")

    departFlights, returnFlights = [], []
    if payload['tripType'] == 'roundtrip':
        if len(priceMatrixes) != 2:
            raise Exception("Only one set of prices returned for round-trip travel")

        elements = priceMatrixes[0].find_elements(by=By.CLASS_NAME, value="air-booking-select-detail")
        departFlights += [scrapeFlights(e) for e in elements]

        elements = priceMatrixes[1].find_elements(by=By.CLASS_NAME, value="air-booking-select-detail")
        returnFlights += [scrapeFlights(e) for e in elements]
    else:
        for element in priceMatrixes[0].find_elements(by=By.CLASS_NAME, value="air-booking-select-detail"):
            departFlights.append(scrapeFlights(element))

    return departFlights, returnFlights
