import configparser
import re

class configurationNotificationSmtp(object):

	def __init__(self, cp):

		self.type = 'smtp'

		if(cp.has_section('smtp') == False):
			raise Exception("Configuration file does not contain 'smtp' section'")

		if(cp.has_option('smtp', 'host')):
			self.host = cp.get('smtp', 'host')
		else:
			raise Exception("Configuration for SMTP missing required 'host' option")

		self.port = cp.getint('smtp', 'port') if cp.has_option('smtp','port') else 25

		if(cp.has_option('smtp', 'recipient')):
			self.recipient = cp.get('smtp', 'recipient')
		else:
			raise Exception("Configuration for SMTP missing required 'recipient' option")

		if(cp.has_option('smtp', 'sender')):
			self.sender = cp.get('smtp', 'sender')
		else:
			raise Exception("Configuration for SMTP missing required 'sender' option")

		self.useAuth = False
		if(cp.has_option('smtp', 'username')):
			self.username = cp.get('smtp', 'username')
			self.useAuth = True
			if(cp.has_option('smtp', 'password')):
				self.password = cp.get('smtp', 'password')
			else:
				raise Exception("Configuration for SMTP has username specified, but not password")

class configurationNotificationTwilio(object):

	def __init__(self, cp):

		self.type = 'twilio'

		if(cp.has_option('twilio', 'accountSid')):
			self.accountSid = cp.get('twilio', 'accountSid')
		else:
			raise Exception("Configuration for Twilio missing required 'accountSid' option")

		if(cp.has_option('twilio', 'authToken')):
			self.authToken = cp.get('twilio', 'authToken')
		else:
			raise Exception("Configuration for Twilio missing required 'authToken' option")

		if(cp.has_option('twilio', 'sender')):
			self.sender = cp.get('twilio', 'sender')
		else:
			raise Exception("Configuration for Twilio missing required 'sender' option")

		if(cp.has_option('twilio', 'recipient')):
			self.recipient = cp.get('twilio', 'recipient')
		else:
			raise Exception("Configuration for Twilio missing required 'recipient' option")

class configurationNotificationNone(object):

	def __init__(self, cp):

		self.type = 'none'


class configurationBrowserChrome(object):

	def __init__(self, cp):

		self.type = 'chrome'

		if(cp.has_section('chrome') == False):
			raise Exception("Configuration file does not contain 'chrome' section")

		if(cp.has_option('chrome', 'binaryLocation')):
			self.binaryLocation = cp.get('chrome', 'binaryLocation')
		else:
			raise exception("For chrome browser configuration, required option binaryLocation is missing")

			# INFO = 0, WARNING = 1, LOG_ERROR = 2, LOG_FATAL = 3
		self.logLevel=3
		if(cp.has_option('chrome', 'logLevel')):
			self.logLevel = cp.getint('chrome', 'logLevel')

class configurationBrowserFirefox(object):

	def __init__(self, cp):

		self.type = 'firefox'

		if(cp.has_section('firefox') == False):
			raise Exception("Configuration file does not contain 'chrome' section")

		if(cp.has_option('firefox', 'binaryLocation')):
			self.binaryLocation = cp.get('firefox', 'binaryLocation')
		else:
			raise exception("For firefox browser configuration, required option binaryLocation is missing")



class configurationTrip(object):

	def __init__(self, cp, section, index):

		self.index = index

		if(cp.has_option(section, 'description')):
			self.description = section + "/" + cp.get(section, 'description')
		else:
			self.description = section

		if(cp.has_option(section, 'originationAirportCode')):
			self.originationAirportCode = cp.get(section, 'originationAirportCode')
		else:
			raise Exception("For section '" + section + "', required option originationAirportCode is missing")

		if(cp.has_option(section, 'destinationAirportCode')):
			self.destinationAirportCode = cp.get(section, 'destinationAirportCode')
		else:
			raise Exception("For section '" + section + "', required option destinationAirportCode is missing")

		if(cp.has_option(section, 'type')):
			self.type = cp.get(section, 'type')
		else:
			raise Exception("For section '" + section + "', required option type is missing")

		if(cp.has_option(section, 'departureDate')):
			self.departureDate = cp.get(section, 'departureDate')
		else:
			raise Exception("For section '" + section + "', required option departureDate is missing")

		self.departureTimeOfDay = cp.get(section, 'departureTimeOfDay') if cp.has_option(section,'departureTimeOfDay') else 'anytime'

		self.returnDate = cp.get(section, 'returnDate') if cp.has_option(section,'returnDate') else ''
		self.returnTimeOfDay = cp.get(section, 'returnTimeOfDay') if cp.has_option(section,'returnTimeOfDay') else 'anytime'

		self.specificFlights = cp.get(section, 'specificFlights') if cp.has_option(section,'specificFlights') else ''

		if(cp.has_option(section, 'adultPassengersCount')):
			self.adultPassengersCount = cp.getint(section, 'adultPassengersCount')
		else:
			raise Exception("For section '" + section + "', required option adultPassengersCount is missing")

		self.maxStops = cp.getint(section, 'maxStops') if cp.has_option(section,'maxStops') else 8 # Just a large value...
		self.maxPrice = cp.getint(section, 'maxPrice') if cp.has_option(section,'maxPrice') else 0

		self.maxDuration = cp.getfloat(section, 'maxDuration') if cp.has_option(section,'maxDuration') else 0.0

class configuration(object):

	def __init__(self, configurationFile):

		cp = configparser.SafeConfigParser()
		cp.read(configurationFile)

		if(cp.has_section('global') == False):
			raise Exception("Configuration file does not contain 'global' section'")

		self.pollInterval = 30
		if(cp.has_option('global', 'pollInterval') and (cp.getint('global', 'pollInterval') >= 5)):
			self.pollInterval = cp.getint('global', 'pollInterval')

		if(cp.has_option('global', 'debug')):
			self.debug = cp.getboolean('global', 'debug')
		else:
			self.debug = False

		if(cp.has_option('global', 'dailyAlerts')):
			self.dailyAlerts = cp.getboolean('global', 'dailyAlerts')
		else:
			self.dailyAlerts = False

		if(cp.has_option('global', 'notificationMethod')):
			self.notificationMethod = cp.get('global', 'notificationMethod')
		else:
			raise Exception("Unspecified notificationMethod")

		if(self.notificationMethod == 'smtp'):
			self.notification = configurationNotificationSmtp(cp)
		elif(self.notificationMethod == 'twilio'):
			self.notification = configurationNotificationTwilio(cp)
		elif(self.notificationMethod == 'none'):
			self.notification = configurationNotificationNone(cp)
		else:
			raise Exception("Unrecognized notificationMethod '" + self.notificationMethod + "'")

		if(cp.has_option('global', 'browser')):
			self.browser = cp.get('global', 'browser')
		else:
			raise Exception("Unspecified browser")

		if(self.browser == 'chrome'):
			self.browser = configurationBrowserChrome(cp)
		elif(self.browser == 'firefox'):
			self.browser = configurationBrowserFirefox(cp)
		else:
			raise Exception("Unrecognized browser '" + self.browser + "'")

		if(cp.has_option('global', 'historyFileBase')):
			self.historyFileBase = cp.get('global', 'historyFileBase')
		else:
			self.historyFileBase = ''

		i = 0;
		self.trips = []
		pattern = re.compile("^trip-[0-9]+$")
		for section in cp.sections():
			if(not pattern.match(section)):
				continue

			self.trips.append(configurationTrip(cp, section, i))

			i += 1

		if(len(self.trips) == 0):
			raise Exception("Configuration file must have at least one [trip-X] section")

		return
