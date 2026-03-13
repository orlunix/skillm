.PHONY: build install clean test

# Build standalone binary
build:
	python -m PyInstaller --onefile --name skillm --collect-submodules=skillm skillm_entry.py

# Install binary to /usr/local/bin (shared by all users)
install: build
	sudo cp dist/skillm /usr/local/bin/skillm
	sudo chmod 755 /usr/local/bin/skillm

# Install to a custom shared path
install-shared: build
	cp dist/skillm $(DESTDIR)/skillm
	chmod 755 $(DESTDIR)/skillm

clean:
	rm -rf build/ dist/ *.spec

test:
	python -m pytest
