
PLUGINSRC = TR64RouterMonitor
PLUGINDEST = TR64RouterMonitor.indigoPlugin
WORKDIR = "$(PLUGINSRC)/Contents/Server Plugin"

all: install

install-requests: $(WORKDIR)/requests
	git

install-simpletr64: $(WORKDIR)/simpletr64


build:
	rm -rf $(PLUGINDEST)
	cp -r $(PLUGINSRC) $(PLUGINDEST)
	find $(PLUGINDEST) -name "*.pyc" -exec rm -f {} \;
	find $(PLUGINDEST) -name "__pycache__" -exec rm -rf {} \;

install: build install-requests install-simpletr64
	open $(PLUGINDEST)

install-nogit: build
	open $(PLUGINDEST)






