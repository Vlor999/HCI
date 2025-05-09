#include <iostream>
#include <string>
#include <curl/curl.h>
#include <regex>
#include <sstream>

using namespace std;

size_t WriteCallback(void* contents, size_t size, size_t nmemb, std::string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}


std::string query_llm(const std::string& prompt, const std::string& model, int timeout = 120) {
    CURL* curl;
    CURLcode res;
    std::string readBuffer;

    curl = curl_easy_init();
    if (curl) {
        std::string url = "http://localhost:11434/api/generate";
        std::string requestBody = "{\"model\":\"" + model + "\",\"prompt\":\"" + prompt + "\"}";

        struct curl_slist* headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, requestBody.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout);

        res = curl_easy_perform(curl);
        if (res != CURLE_OK) {
            std::cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << std::endl;
        }

        curl_easy_cleanup(curl);
    }

    std::ostringstream fullResponse;
    std::istringstream stream(readBuffer);
    std::string line;
    bool done = false;

    while (std::getline(stream, line)) {
        if (line.find("\"response\":") != std::string::npos) {
            size_t start = line.find("\"response\":") + 10;
            size_t newStart = line.find("\"", start) + 1;
            size_t end = line.find("\"", newStart);
            if (end != string::npos) {
                fullResponse << line.substr(newStart, end - newStart);
            } else {
                fullResponse << line.substr(newStart);
            }
        }

        if (line.find("\"done\":true") != std::string::npos) {
            done = true;
            break;
        }
    }
    return done ? fullResponse.str() : "Error: Response not completed";
}

int main() {
    std::string question = "What's the color of the sun?";
    std::string model = "mistral:7b-instruct-v0.3-fp16";


    auto start = std::chrono::high_resolution_clock::now();
    std::string response = query_llm(question, model);
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> elapsed = end - start;

    std::cout << "Execution time: " << elapsed.count() << " seconds" << std::endl;

    std::cout << "Question: " << question << std::endl;
    std::cout << "Answer: " << response << std::endl;

    return 0;
}
