import logging

from django.conf import settings

from raven import Client
from celery import signature
from logstash import TCPLogstashHandler


class BaseSender(object):
    name = None
    client = None

    def send(self, message, extra={}, tags={}, data={}, crash_obj=None):
        pass


class SentrySender(BaseSender):
    name="Sentry"

    def __init__(self):
        self.client = Client(
            getattr(settings, 'RAVEN_DSN_STACKTRACE', None),
            name=getattr(settings, 'HOST_NAME', None),
            release=getattr(settings, 'APP_VERSION', None)
        )

    def send(self, message, extra={}, tags={}, data={}, crash_obj=None):
        event_id = self.client.capture(
            'raven.events.Message',
            message='chad ' + message,
            extra=extra,
            tags=tags,
            data=data
        )
        signature("tasks.get_sentry_link", args=(crash_obj.pk, event_id)).apply_async(queue='private', countdown=1)


class ELKSender(BaseSender):
    name="ELK"
    handler = None

    def __init__(self):
        host = getattr(settings, 'LOGSTASH_HOST', None)
        port = getattr(settings, 'LOGSTASH_PORT', None)
        if host and port:
            self.handler = TCPLogstashHandler(host, int(port))
        else:
            logging.error("Logstash settings are not configured")

    def send(self, message, extra={}, tags={}, data={}, crash_obj=None):
        if self.handler:
            logger = self._prepare_logger()
            extra.update(tags)
            extra.update(data)
            extra.update({'logger_name': 'omahaserver'})
            logger.info(message, extra=extra)
        else:
            logging.error("Logstash settings are not configured")

    def _prepare_logger(self):
        """It's a workaround.

        If we do it in __init__ then logger won't send messages to Logstash
        """
        logger = logging.getLogger('crash_sender')
        logger.setLevel(logging.INFO)
        logger.handlers = []
        logger.addHandler(self.handler)
        return logger


senders_dict = {
    "Sentry": SentrySender,
    "ELK": ELKSender,
}


def get_sender(tracker_name=None):
    if not tracker_name:
        tracker_name = getattr(settings, 'CRASH_TRACKER', 'Sentry')
    try:
        sender_class = senders_dict[tracker_name]
    except KeyError:
        raise KeyError("Unknown tracker, use one of %s" % senders_dict.keys())
    return sender_class()
