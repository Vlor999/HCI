TEX=pdflatex
BIBTEX=bibtex
SRC=main.tex

all: pdf

pdf:
	$(TEX) $(SRC)
	$(BIBTEX) main
	$(TEX) $(SRC)
	$(TEX) $(SRC)

clean:
	latexmk -c

.PHONY: all pdf clean
