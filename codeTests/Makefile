FILE = llama
CC = g++
CXXFLAGS = -std=c++23 -I/opt/homebrew/include -lcurl
SRC = llama.cpp
OUT = out

all: run

creation:
	mkdir -p $(OUT)

compile: $(SRC)
	$(CC) $(CXXFLAGS) $< -o $(OUT)/$(FILE)

run: creation compile
	./$(OUT)/$(FILE)

clean:
	rm -f $(FILE)
