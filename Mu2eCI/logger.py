import logging

LOG_LEVEL = logging.DEBUG
LOG_LEVEL_FILE = logging.DEBUG
LOG_FORMAT = "[%(asctime)s] %(name)s:%(levelname)s  |  %(message)s"
LOG_FILE = "Mu2eCI.log"

stream = logging.StreamHandler()
stream.setLevel(LOG_LEVEL)
stream.setFormatter(logging.Formatter(LOG_FORMAT))

streamf = logging.FileHandler(LOG_FILE)
streamf.setLevel(LOG_LEVEL_FILE)
streamf.setFormatter(logging.Formatter(LOG_FORMAT))

log = logging.getLogger("Mu2eCI")

log.setLevel(LOG_LEVEL)
log.addHandler(stream)
log.addHandler(streamf)
