FILE = llama
CC = g++
CXXFLAGS = -std=c++23 -I/opt/homebrew/include -lcurl
SRC = llama.cpp
OUT = out

all: run

compile: $(SRC)
	$(CC) $(CXXFLAGS) $< -o $(OUT)/$(FILE)

run: compile
	./$(OUT)/$(FILE)

clean:
	rm -f $(FILE)
