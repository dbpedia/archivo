import logging


discovery_log_path = "./logs/discovery.log"
webservce_log_path = "./logs/webservice.log"
diff_log_path = "./logs/diff.log"


webservice_logger = logging.getLogger("webservice")
discovery_logger = logging.getLogger("discovery")
diff_logger = logging.getLogger("difflog")


# Handlers handling files & streams

console_handler = logging.StreamHandler()
webservice_file_handler = logging.FileHandler(webservce_log_path)
discovery_file_handler = logging.FileHandler(discovery_log_path)
diff_file_handler = logging.FileHandler(diff_log_path)

# set the base level of loggers
for logger in [webservice_logger, discovery_logger, diff_logger]:
    logger.setLevel(logging.DEBUG)

# Formatters and adding the to the handlers
c_format = logging.Formatter("[%(levelname)s]:[%(name)s]:%(message)s")
console_handler.setFormatter(c_format)
file_format = logging.Formatter("[%(asctime)s]:[%(levelname)s]:%(message)s")
for f_handler in [webservice_file_handler, discovery_file_handler, diff_file_handler]:
    f_handler.setLevel(logging.DEBUG)
    f_handler.setFormatter(file_format)
console_handler.setLevel(logging.ERROR)

# add right handlers to the right logger

discovery_file_handler

webservice_logger.addHandler(console_handler)
webservice_logger.addHandler(webservice_file_handler)
discovery_logger.addHandler(console_handler)
discovery_logger.addHandler(discovery_file_handler)
diff_logger.addHandler(console_handler)
diff_logger.addHandler(diff_file_handler)
