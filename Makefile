# oathpass -- answer an SSH OATH/TOTP prompt from a local seed.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -Werror
PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
BIN      = oathpass

.PHONY: all install uninstall check test clean

all: $(BIN)

$(BIN): scripts/oathpass.c
	$(CC) $(CFLAGS) -o $@ $<

# The build output is the command, so installing is one copy -- no interpreter,
# no symlink, no bytecode cache.
install: $(BIN)
	mkdir -p $(BINDIR)
	install -m 0755 $(BIN) $(BINDIR)/$(BIN)
	@echo "installed $(BINDIR)/$(BIN)"
	@command -v $(BIN) >/dev/null 2>&1 && echo "$(BIN) is on PATH" || \
		echo "warning: $(BINDIR) is not on PATH -- add it to your shell profile"

uninstall:
	rm -f $(BINDIR)/$(BIN)

# Does the installed binary answer correctly and is it reachable by name?
check: install
	$(BIN) --selftest
	@command -v $(BIN) >/dev/null 2>&1 || { echo "$(BIN) is not on PATH"; exit 1; }

test: $(BIN)
	./$(BIN) --selftest

clean:
	rm -f $(BIN)
