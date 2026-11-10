BIOME_VERSION        := 2.6.6
PHP_VERSION          := 8.5.8
PHP_CS_FIXER_VERSION := 3.95.30
PHPUNIT_VERSION      := 12.5.43
PINACT_VERSION       := 5.0.2
TAPLO_VERSION        := 0.10.0
YAMLFMT_VERSION      := 0.21.0

all: biome php php-cs-fixer phpunit pinact taplo yamlfmt

biome:
	mkdir -p biome
	wget https://github.com/biomejs/biome/releases/download/%40biomejs%2Fbiome%40$(BIOME_VERSION)/biome-linux-x64 \
	    -O biome/biome
	chmod +x biome/biome

php:
	mkdir -p php
	wget https://dl.static-php.dev/static-php-cli/common/php-$(PHP_VERSION)-cli-linux-x86_64.tar.gz \
	    -O php.tar.gz
	tar xzf php.tar.gz -C php
	rm -f php.tar.gz

php-cs-fixer:
	mkdir -p php-cs-fixer
	wget https://github.com/PHP-CS-Fixer/PHP-CS-Fixer/releases/download/v$(PHP_CS_FIXER_VERSION)/php-cs-fixer.phar \
	    -O php-cs-fixer/php-cs-fixer.phar
	chmod +x php-cs-fixer/php-cs-fixer.phar

phpunit:
	mkdir -p phpunit
	wget https://phar.phpunit.de/phpunit-$(PHPUNIT_VERSION).phar \
	    -O phpunit/phpunit.phar
	chmod +x phpunit/phpunit.phar

pinact:
	mkdir -p pinact
	wget https://github.com/suzuki-shunsuke/pinact/releases/download/v$(PINACT_VERSION)/pinact_linux_amd64.tar.gz \
	    -O pinact.tar.gz
	tar xzf pinact.tar.gz -C pinact
	rm -f pinact.tar.gz

taplo:
	mkdir -p taplo
	wget https://github.com/tamasfe/taplo/releases/download/$(TAPLO_VERSION)/taplo-linux-x86_64.gz \
	    -O taplo.gz
	gunzip -c taplo.gz > taplo/taplo
	chmod +x taplo/taplo
	rm -f taplo.gz

yamlfmt:
	mkdir -p yamlfmt
	wget https://github.com/google/yamlfmt/releases/download/v$(YAMLFMT_VERSION)/yamlfmt_$(YAMLFMT_VERSION)_Linux_x86_64.tar.gz \
	    -O yamlfmt.tar.gz
	tar xzf yamlfmt.tar.gz -C yamlfmt
	rm -f yamlfmt.tar.gz

clean:
	rm -rf biome php php-cs-fixer phpunit pinact taplo yamlfmt

.PHONY: all clean
