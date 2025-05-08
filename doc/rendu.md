# My roadmap

## Different steps :
### How to use llms (15 april)

Firstly I had to found a way to speak to an [llm localy](https://semaphore.io/blog/local-llm) and it appeared that the easiest way was to do it thanks to [ollama](https://ollama.com/). But It may be more efficient to use also [Llama.cpp](https://github.com/ggml-org/llama.cpp) which may be a futur optimization. For now i will only use a simple styff with ollama.

### Literature Review (15 - 20 april)
#### Technologies and methodologies in human-robot communication
* Dialogue management in human-robot interaction :
    * This [review](https://arxiv.org/abs/2307.10897) analyzes the current use of dialogue management in human robot interaction, mainly about dialogue managers used. How they **evaluate** capabilities, methods and challenges specific to dialogue management in human robot interaction. It highlights the need for structural approaches to combine HRI and dialogue effectively.
* Human–robot interaction overview
    * This [overview](https://en.wikipedia.org/wiki/Human%E2%80%93robot_interaction) sepaks about human–robot interactions, emphasizing the importance of **intuitive** communication through speech, gestures, and facial expressions. It also shows that **feel** human is a goal for the robot and for the interactions.

#### Interpretability of low-level perception information in robotics
* Explainable robotic systems in reinforcement learning scenarios
    * This [document](https://arxiv.org/abs/2006.13615) focuses on the decision-making processes of reinforcement learning agents in robotic scenarios. It introduces methods to explain robots actions using the probabilities computed.
* Subsumption architecture
    * This [file](https://en.wikipedia.org/wiki/Subsumption_architecture) discusses about an approach to robotics that emphasizes real-time interaction and viable responses to dynamic environments. It highlights the importance of situatedness, embodiment, and emergence in developing intelligent robotic behaviors.

#### Challenges and opportunities in making robotic actions and decisions understandable to human users
* Trust considerations for explainable robots
    * This [paper](https://arxiv.org/abs/2005.05940) explores how trust can be built and maintained in explainable robots. It explores concepts like trust calibration and specificity. Discuss ways to measure trust through explanations provided by robots. These insights could help design systems that feel more reliable and transparent to users.
* Effects of explanations in human robot interaction
    * This [study](https://arxiv.org/abs/2005.05940) analyzes the effects of robot explanations on human perceptions during interactions. It finds that while explanations may not significantly change perceptions of competence or safety, they can make robots appear more lively and human-like.
* Ethical Black Box for Robots
    * Professor [Marina Jirotka's](https://en.wikipedia.org/wiki/Marina_Jirotka) work on the `ethical black box` proposes that robots using AI should be equipped with a type of inflight recorder to track decisions and actions. This concept aims to enhance transparency and accountability in robotic systems.

### Implementation and issues
#### First steps
To start I had to found models on ollama which could fit on my computer but that also would be efficicent for the robot. So I read lots of article about the size compare to the computer you have. In my part I tried with 3 models :

| **Name**                          | **ID**          | **Size**  |
|-----------------------------------|-----------------|-----------|
| mistral:7b-instruct-v0.3-fp16     | 1729fae719f1    | 14 GB     |
| deepseek-r1:7b-qwen-distill-q8_0  | 0bcb1414f90e    | 8.1 GB    |
| llama3.2:latest                   | a80c4f17acd5    | 2.0 GB    |

**WARNING** : Generally if the model have a bigger size he will often be better onto normal [benchmark](https://en.wikipedia.org/wiki/Language_model_benchmark) but will need some more efficient hardware. So before downlaoding a model please take care that this one fit for you computer.

to download one of those you have to run  :
```sh
ollama pull <model-name>
# Exemple :
ollama pull mistral:7b-instruct-v0.3-fp16
```

If you want to run it locally to try it you have to run the next command :

```sh
ollama run <model-name>
# Exemple :
ollama run mistral:7b-instruct-v0.3-fp16
# If the model is too heavy for your local computer it may cause lots of switch into your memory then take a lots of time you launch.
```

#### Second steps
Now it was the fun part I would say. I implemented a `python` project that will read a question from the user, give informations to the llm and receive our answer.

#### Improvment :
Make a local model from ollama models look this [video](https://www.youtube.com/watch?v=Ox8hhpgrUi0&ab_channel=SamWitteveen) to easy understant and how to launch ollama on your computer.

#### Issues
1. I wanted each time an answer does not fit to tyyhe question make some corrections about that but now wich one of my model there is some over fitting : when I'm asking the fastest road I always do have the two fastest ones.

## Information :
My computer :

| **Chip**     | **Memory** |
|--------------|------------|
| Apple M4 Pro | 24GB       |
