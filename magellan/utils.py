from pythonjsonlogger import jsonlogger

class StackdriverJsonFormatter(jsonlogger.JsonFormatter):
    """
    JSON log formatter that's Google Stackdriver friendly.
    """
    def add_fields(self, log_record, record, message_dict):
        super(StackdriverJsonFormatter, self).add_fields(log_record, record,
            message_dict)
        log_record['severity'] = record.levelname
