#include <iostream>
#include <string>
#include <curl/curl.h>
#include <regex>
#include <sstream>
#include <chrono>
#include <nlohmann/json.hpp>

using json = nlohmann::json;
using namespace std;

size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    string chunk((char*)contents, size * nmemb);
    ostringstream* fullBuffer = static_cast<ostringstream*>(userp);

    istringstream stream(chunk);
    string line;

    while (getline(stream, line)) {
        if (line.empty()) continue;

        try {
            json j = json::parse(line);

            if (j.contains("response")) {
                cout << j["response"].get<string>() << flush;
            }

            (*fullBuffer) << line << "\n";
        } catch (const json::parse_error& e) {
            cerr << "\n[JSON parse error] " << e.what() << "\n";
        }
    }

    return size * nmemb;
}

void query_llm(const string& prompt, const string& model, int timeout = 120) {
    CURL* curl;
    CURLcode res;
    ostringstream fullResponse;

    curl = curl_easy_init();
    if (curl) {
        string url = "http://localhost:11434/api/generate";
        string requestBody = "{\"model\":\"" + model + "\",\"prompt\":\"" + prompt + "\",\"stream\":true}";

        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, requestBody.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &fullResponse);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout);
        curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);  // Set to 1L for debug

        res = curl_easy_perform(curl);
        if (res != CURLE_OK) {
            cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << endl;
        }

        curl_easy_cleanup(curl);

        // Post-processing full JSON lines to extract final stats
        istringstream stream(fullResponse.str());
        string line;
        json lastJson;

        while (getline(stream, line)) {
            try {
                lastJson = json::parse(line);
                if (lastJson.contains("done") && lastJson["done"] == true) {
                    break;
                }
            } catch (...) {
                continue;
            }
        }

        if (!lastJson.empty()) {
            cout << "\n\n--- Ollama Stats ---" << endl;
            if (lastJson.contains("total_duration"))
                cout << "Total duration: " << lastJson["total_duration"] << " ns" << endl;
            if (lastJson.contains("load_duration"))
                cout << "Load duration: " << lastJson["load_duration"] << " ns" << endl;
            if (lastJson.contains("eval_duration"))
                cout << "Eval duration: " << lastJson["eval_duration"] << " ns" << endl;
            if (lastJson.contains("prompt_eval_count"))
                cout << "Prompt tokens: " << lastJson["prompt_eval_count"] << endl;
            if (lastJson.contains("eval_count"))
                cout << "Generated tokens: " << lastJson["eval_count"] << endl;
        }
    }
}

int main() {
    string question = "What's the color of the sun?";
    string model = "mistral:7b-instruct-v0.3-fp16";

    cout << "Question: " << question << "\n\n";
    query_llm(question, model);
    return EXIT_SUCCESS;
}
