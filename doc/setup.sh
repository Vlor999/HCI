#!/bin/bash

mkdir -p robot-explain-yourself/{sections,figures}
cd robot-explain-yourself

touch main.tex bibliography.bib

for section in 01-introduction 02-literature-review 03-framework-design 04-llm-customization 05-hri-prototype 06-evaluation 07-conclusion; do
    touch sections/${section}.tex
done

touch figures/system-architecture.pdf
touch figures/hri-interface.png
touch figures/evaluation-graph.pdf

touch evaluation-report.pdf
touch presentation.pdf

echo "Project structure created successfully!"
