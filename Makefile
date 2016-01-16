
PLUGINSRC = TR64RouterMonitor
PLUGINDEST = TR64RouterMonitor.indigoPlugin
WORKDIR = Contents/Server\ Plugin
CONFDIR = Contents
VERSIONFILE = $(CONFDIR)/counter
CONFFILE = $(CONFDIR)/Info.plist
DISTDIR = dist

all: install

install-requests:
	@echo "Dependency: requests, start"
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf requests;svn checkout https://github.com/kennethreitz/requests/trunk/requests > /dev/null
	@echo "Dependency: requests, done"

install-simpletr64:
	@echo "Dependency: simpletr64, start"
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf simpletr64;svn checkout https://github.com/bpannier/simpletr64/trunk/simpletr64 > /dev/null
	@echo "Dependency: simpletr64, done"

build:
	@echo "Create package"
	@rm -rf $(PLUGINDEST)
	@touch $(PLUGINSRC)/$(VERSIONFILE)
	@perl -e '$$number = `cat $(PLUGINSRC)/$(VERSIONFILE)`;chomp($$number);($$number =~ /^\s*$$/)? $$number = 0 : $$number++;`echo $$number > $(PLUGINSRC)/$(VERSIONFILE)`;'
	@cp -r $(PLUGINSRC) $(PLUGINDEST)
	@rm -f $(PLUGINDEST)/$(VERSIONFILE)
	@perl -e '$$number = `cat $(PLUGINSRC)/$(VERSIONFILE)`;chomp($$number);print "Version: $$number\n";`cat $(PLUGINSRC)/$(CONFFILE) | sed \"s/REPLACEME/$$number/\" > $(PLUGINDEST)/$(CONFFILE)`;'
	@find $(PLUGINDEST) -name "*.pyc" -delete
	@find $(PLUGINDEST) -name "__pycache__" -delete
	@find $(PLUGINDEST) -name '*.DS_Store' -type f -delete
	@echo "Package created"

clean:
	@rm -rf $(PLUGINDEST)
	@find $(PLUGINSRC) -name "*.pyc" -delete
	@find $(PLUGINSRC) -name "__pycache__" -delete
	@find $(PLUGINSRC) -name '*.DS_Store' -type f -delete
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf requests
	@cd $(PLUGINSRC)/$(WORKDIR);rm -rf simpletr64

install: install-requests install-simpletr64 build
	@echo "Install plugin..."
	open $(PLUGINDEST)
	@echo "Done"

install-local: build
	@echo "Install plugin..."
	open $(PLUGINDEST)
	@echo "Done"

publish: install-requests install-simpletr64 build
	@zip -qr9 $(PLUGINSRC).zip $(PLUGINDEST)
	@perl -e 'local $$/;open(FILE,"$(PLUGINDEST)/$(CONFFILE)") || die "can not open config file";$$_ = <FILE>;/PluginVersion[^>]+>[^>]+>\s*([^<]+)\s*</i || die "can not find version"; $$version = $$1; $$version =~ s/\./_/g; `mv $(PLUGINSRC).zip $(DISTDIR)/$(PLUGINSRC)-$$version.zip`;`cp $(DISTDIR)/$(PLUGINSRC)-$$version.zip $(DISTDIR)/$(PLUGINSRC)-latest.zip`;`git add -f $(DISTDIR)/$(PLUGINSRC)-$$version.zip`; print "Version: $$version\n" '

deinstall:
	@rm -rf "/Library/Application Support/Perceptive Automation/Indigo 6/Plugins/TR64RouterMonitor.indigoPlugin"
	@rm -rf "/Library/Application Support/Perceptive Automation/Indigo 6/Plugins (Disabled)/TR64RouterMonitor.indigoPlugin"


