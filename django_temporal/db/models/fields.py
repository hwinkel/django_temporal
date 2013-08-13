from datetime import datetime, date, tzinfo, timedelta
import pytz
import re

from django.conf import settings
from django.forms import ValidationError
#from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query_utils import QueryWrapper


__all__ = ['TZDatetime', 'TZDateTimeField', 'TIME_CURRENT', 'Period', 'PeriodField', 'ForeignKey', 'TemporalForeignKey']

class TZDatetime(datetime):
	def aslocaltimezone(self):
		"""Returns the datetime in the local time zone."""
		tz = pytz.timezone(settings.TIME_ZONE)
		return self.astimezone(tz)

# 2009-06-04 12:00:00+01:00 or 2009-06-04 12:00:00 +0100
TZ_OFFSET = re.compile(r'^"?(.*?)\s?([-\+])(\d\d):?(\d\d)?"?$')

TIME_CURRENT = datetime(9999, 12, 31, 23, 59, 59, 999999)
TIME_RESOLUTION = timedelta(0, 0, 1) # = 1 microsecond

class TZDateTimeField(models.DateTimeField):
	"""A DateTimeField that treats naive datetimes as local time zone."""
	__metaclass__ = models.SubfieldBase
	
	def to_python(self, value):
		"""Returns a time zone-aware datetime object.
		
		A naive datetime is assigned the time zone from settings.TIME_ZONE.
		This should be the same as the database session time zone.
		A wise datetime is left as-is. A string with a time zone offset is
		assigned to UTC.
		"""
		try:
			value = super(TZDateTimeField, self).to_python(value)
		except ValidationError:
			match = TZ_OFFSET.search(value)
			if match:
				value, op, hours, minutes = match.groups()
				minutes = minutes is not None and minutes or '0'
				value = super(TZDateTimeField, self).to_python(value)
				value = value - timedelta(hours=int(op + hours), minutes=int(op + minutes))
				value = value.replace(tzinfo=pytz.utc)
			else:
				raise
		
		if value is None:
			return value
		
		# Only force zone if the datetime has no tzinfo
		#if (value.tzinfo is None) or (value.tzinfo.utcoffset(value) is None):
		#	value = force_tz(value, settings.TIME_ZONE)
		return TZDatetime(value.year, value.month, value.day, value.hour,
			value.minute, value.second, value.microsecond, tzinfo=value.tzinfo)

def force_tz(obj, tz):
	"""Converts a datetime to the given timezone.
	
	The tz argument can be an instance of tzinfo or a string such as
	'Europe/London' that will be passed to pytz.timezone. Naive datetimes are
	forced to the timezone. Wise datetimes are converted.
	"""
	if not isinstance(tz, tzinfo):
		tz = pytz.timezone(tz)
	
	if (obj.tzinfo is None) or (obj.tzinfo.utcoffset(obj) is None):
		return tz.localize(obj)
	else:
		return obj.astimezone(tz)


class Period(object):
	def __init__(self, period=None, start=None, end=None):
		if isinstance(period, datetime): # XXX FIXME argument rewriting isn't ok
			start, end, period = period, start, None
		if not (isinstance(period, (basestring, self.__class__)) or isinstance(start, datetime)):
			raise TypeError("You must specify either period (string or Period) or start (TZDatetime or datetime.datetime).")
		
		if period is not None:
			if isinstance(period, basestring):
				m = re.match('^([\[\(])([^,]+),([^\]\)]+)([\]\)])$', period.strip())
				if not m:
					raise TypeError("Invalid period string representation: %s" % repr(period))
				start_in, start, end, end_in = m.groups()
				
				
				self.start = TZDateTimeField().to_python(start.strip())
				self.end = TZDateTimeField().to_python(end.strip())
				if start_in == '[':
					self.start_included = True
				else:
					self.start_included = False
				
				if end_in == ']':
					self.end_included = True
				else:
					self.end_included = False
				
				
			elif isinstance(period, self.__class__):
				self.start = period.start
				self.end = period.end
				self.start_included = period.start_included
				self.end_included = period.end_included
		else:
			self.start = start
			self.start_included = True
			if end is not None:
				self.end = end
				self.end_included = False
			else:
				self.end = TIME_CURRENT
				self.end_included = True
	
	def start():
		def fget(self):
			return self.__start
		def fset(self, value):
			if isinstance(value, TZDatetime):
				self.__start = value.replace(tzinfo=None)
			elif isinstance(value, datetime):
				self.__start = TZDateTimeField().to_python(value.strftime(u'%Y-%m-%d %H:%M:%S.%f%z')).replace(tzinfo=None)
			else:
				raise AssertionError("should never happen")
		return (fget, fset, None, "start of period")
	start = property(*start())
	
	def start_included():
		def fget(self):
			return self.__start_included
		def fset(self, value):
			if not value in (True, False):
				raise ValueError("Must be True or False")
			if not value:
				self.start = self.start + TIME_RESOLUTION
				value = True
			self.__start_included = value
		return (fget, fset, None, "denotes if start timestamp is open or closed")
	start_included = property(*start_included())
	
	def end():
		def fget(self):
			return self.__end
		def fset(self, value):
			if isinstance(value, TZDatetime):
				self.__end = value.replace(tzinfo=None)
			elif isinstance(value, datetime):
				self.__end = TZDateTimeField().to_python(value.strftime(u'%Y-%m-%d %H:%M:%S.%f%z')).replace(tzinfo=None)
			else:
				raise AssertionError("should never happen")
		return (fget, fset, None, "end of period")
	end = property(*end())
	
	def end_included():
		def fget(self):
			return self.__end_included
		def fset(self, value):
			if not value in (True, False):
				raise ValueError("Must be True or False")
			if value:
				self.end = self.end + TIME_RESOLUTION
				value = False
			self.__end_included = value
		return (fget, fset, None, "denotes if end timestamp is open or closed")
	end_included = property(*end_included())
	
	def __eq__(self, other):
		if  self.start_included == other.start_included and \
			self.end_included == other.end_included and \
			self.start == other.start and\
			self.end == other.end:
			return True
		return False
	
	
	
	def is_current(self):
		if self.end == TIME_CURRENT and self.end_included == False:
			return True
		return False
	
	def set_current(self):
		self.end = TIME_CURRENT
		self.end_included = False
	
	def first(self):
		return self.start
	
	def prior(self):
		return self.start - TIME_RESOLUTION
	
	def last(self):
		return self.end - TIME_RESOLUTION
	
	def next(self):
		return self.end
	
	def __unicode__(self):
		return u''.join([
			self.start_included and u'[' or u'(',
			self.start.replace(tzinfo=pytz.UTC).strftime(u'%Y-%m-%d %H:%M:%S.%f%z'),
			u',',
			self.end.replace(tzinfo=pytz.UTC).strftime(u'%Y-%m-%d %H:%M:%S.%f%z'),
			self.end_included and ']' or ')',
			])
	
	def __repr__(self):
		return '<Period from %s to %s>' % (self.start.strftime('%Y-%m-%d %H:%M:%S.%f%z'), self.end.strftime('%Y-%m-%d %H:%M:%S.%f%z'))
		

class PeriodField(models.Field):
	description = 'A period of time'
	
	__metaclass__ = models.SubfieldBase
	
	def __init__(self, verbose_name=None, sequenced_key=None, current_unique=None, sequenced_unique=None, nonsequenced_unique=None, not_empty=True, **kwargs):
		
		kwargs['verbose_name'] = verbose_name
		
		self.sequenced_key = sequenced_key
		
		self.current_unique = current_unique
		self.sequenced_unique = sequenced_unique
		self.nonsequenced_unique = nonsequenced_unique
		self.not_empty = bool(not_empty)
		
		super(PeriodField, self).__init__(**kwargs)
	
	def db_type(self, connection):
		return 'tstzrange'
		# ALTER TABLE "temporal_incumbent" ADD EXCLUDE USING gist ("ssn_id" WITH =, "pcn_id" WITH =, "valid_time" WITH &&);
		#if self.sequenced_key:
		#	db_column = db_column + ', EXCLUDE USING gist (%s)' % ', '.join(['%s WITH =' % qn(i) for i in self.sequenced_key] + ['%s WITH &&' % qn(self.name)])
	
	def to_python(self, value):
		if isinstance(value, Period):
			return value
		return Period(value)
	
	def get_prep_value(self, value):
		return Period(value)
	
	def get_prep_lookup(self, lookup_type, value):
		if lookup_type in (
				'exact', 'lt', 'lte', 'gt', 'gte', 'nequals', 'contains', 'contained_by',
				'overlaps', 'before', 'after', 'overleft', 'overright', 'adjacent'):
			if not isinstance(value, Period):
				value = Period(value)
			return unicode(value)
		if lookup_type in ('prior', 'first', 'last', 'next'):
			if not isinstance(value, datetime):
				raise # XXX
			return unicode(value)
		raise TypeError("Field has invalid lookup: %s" % lookup_type)
	
	def get_db_prep_lookup(self, lookup_type, value, connection, prepared=False):
		if lookup_type in ('exact', 'lt', 'lte', 'gt', 'gte'):
			return super(PeriodField, self).get_db_prep_lookup(lookup_type=lookup_type, value=value, connection=connection, prepared=prepared)
		elif lookup_type in ('nequals', 'contains', 'contained_by', 'overlaps', 'before', 'after', 'overleft', 'overright', 'adjacent'):
			return [value]
		elif lookup_type in ('prior', 'first', 'last', 'next'):
			return [value]
	
	def get_db_prep_value(self, value, connection, prepared=False):
		if isinstance(value, datetime):
			return models.DateTimeField().get_db_prep_value(value, connection, prepared)
		else:
			return unicode(Period(value))

class ValidTime(PeriodField):
	"Special class in order to be able to know this represents validity"
	pass

class TemporalForeignKey(models.ForeignKey):
	def __init__(self, *args, **kwargs):
		if 'temporal_current' in kwargs:
			self.temporal_current = bool(kwargs.pop('temporal_current'))
		if 'temporal_sequenced' in kwargs:
			self.temporal_sequenced = bool(kwargs.pop('temporal_sequenced'))
		super(TemporalForeignKey, self).__init__(*args, **kwargs)


ForeignKey = TemporalForeignKey

