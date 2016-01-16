
PLUGINSRC = TR64RouterMonitor
PLUGINDEST = TR64RouterMonitor.indigoPlugin
WORKDIR = Contents/Server\ Plugin
CONFDIR = Contents
VERSIONFILE = $(CONFDIR)/counter
CONFFILE = $(CONFDIR)/Info.plist

all: install

install-requests:
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf requests;svn checkout https://github.com/kennethreitz/requests/trunk/requests > /dev/null
	@echo "Dependency: requests, done"

install-simpletr64:
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf simpletr64;svn checkout https://github.com/bpannier/simpletr64/trunk/simpletr64 > /dev/null
	@echo "Dependency: simpletr64, done"

build:
	@rm -rf $(PLUGINDEST)
	@touch $(PLUGINSRC)/$(VERSIONFILE)
	@perl -e '$$number = `cat $(PLUGINSRC)/$(VERSIONFILE)`;$$number++;`echo $$number > $(PLUGINSRC)/$(VERSIONFILE)`;'
	@cp -r $(PLUGINSRC) $(PLUGINDEST)
	@rm -f $(PLUGINDEST)/$(VERSIONFILE)
	@perl -e '$$number = `cat $(PLUGINSRC)/$(VERSIONFILE)`;chomp($$number);print "Version: $$number\n";`cat $(PLUGINSRC)/$(CONFFILE) | sed \"s/REPLACEME/$$number/\" > $(PLUGINDEST)/$(CONFFILE)`;'
	@find $(PLUGINDEST) -name "*.pyc" -delete
	@find $(PLUGINDEST) -name "__pycache__" -delete
	@echo "Package created"

install: install-requests install-simpletr64 build
	@echo "Install plugin..."
	open $(PLUGINDEST)
	@echo "Done"

install-local: build
	@echo "Install plugin..."
	open $(PLUGINDEST)
	@echo "Done"

