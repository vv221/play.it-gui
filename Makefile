.PHONY: all

all: play.all

play.all: play.all.py
	cython -3 --embed -o play.all.c play.all.py
	gcc -o play.all play.all.c -Os -I /usr/include/python3.7m -lpython3.7m -lpthread -lm -lutil -ldl
	rm play.all.c

clean:
	rm -f play.all play.all.c
