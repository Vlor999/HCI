import os
import json
from datetime import datetime
from typing import List, Dict, Any
from src.evaluation.conversationReader import ConversationReader
from src.evaluation.evaluationMetrics import ExplanationEvaluator, EvaluationResult
from src.config.constants import LOG_CONVERSATIONS_DIR


class EvaluationRunner:
    def __init__(self, log_dir: str = LOG_CONVERSATIONS_DIR, output_dir: str = "log/evaluation"):
        self.log_dir = log_dir
        self.output_dir = output_dir
        self.reader = ConversationReader(log_dir)
        self.evaluator = ExplanationEvaluator()

    def run_evaluation(self, save_results: bool = True) -> Dict[str, Any]:
        print(f"🔍 Starting evaluation of conversation logs in {self.log_dir}")

        conversations = self.reader.read_all_conversations()
        if not conversations:
            print("❌ No conversation logs found.")
            return {"error": "No conversation logs found"}

        print(f"📄 Found {len(conversations)} conversation logs to evaluate")

        evaluation_results: list[EvaluationResult] = []
        for conversation in conversations:
            print(f"📊 Evaluating {conversation.filename}...")
            result = self.evaluator.evaluate_conversation(conversation)
            evaluation_results.append(result)

        summary = self.generate_summary(evaluation_results)

        if save_results:
            self.save_results(evaluation_results, summary)

        self.print_summary(summary)
        return summary

    def generate_summary(self, results: List[EvaluationResult]) -> Dict[str, Any]:
        if not results:
            return {"error": "No results to summarize"}

        total_questions = sum(len(r.question_evaluations) for r in results)

        accuracy_scores: list[float] = []
        completeness_scores: list[float] = []
        relevance_scores: list[float] = []
        clarity_scores: list[float] = []
        overall_scores: list[float] = []

        for result in results:
            for _, metrics in result.question_evaluations:
                accuracy_scores.append(metrics.accuracy_score)
                completeness_scores.append(metrics.completeness_score)
                relevance_scores.append(metrics.relevance_score)
                clarity_scores.append(metrics.clarity_score)
                overall_scores.append(metrics.overall_score)

        def safe_average(scores: List[float]) -> float:
            return sum(scores) / len(scores) if scores else 0.0

        summary: dict[str, Any] = {
            "evaluation_timestamp": datetime.now().isoformat(),
            "total_conversations": len(results),
            "total_questions": total_questions,
            "overall_metrics": {
                "accuracy": safe_average(accuracy_scores),
                "completeness": safe_average(completeness_scores),
                "relevance": safe_average(relevance_scores),
                "clarity": safe_average(clarity_scores),
                "overall": safe_average(overall_scores),
            },
            "conversation_summaries": [
                {
                    "filename": result.conversation_log.filename,
                    "questions_count": len(result.question_evaluations),
                    "avg_accuracy": result.average_metrics.accuracy_score,
                    "avg_completeness": result.average_metrics.completeness_score,
                    "avg_relevance": result.average_metrics.relevance_score,
                    "avg_clarity": result.average_metrics.clarity_score,
                    "avg_overall": result.average_metrics.overall_score,
                }
                for result in results
            ],
        }

        return summary

    def save_results(self, results: List[EvaluationResult], summary: Dict[str, Any]) -> None:
        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        detailed_results: list[dict[str, Any]] = []
        for result in results:
            detailed_result: dict[str, Any] = {
                "conversation_info": {
                    "filename": result.conversation_log.filename,
                    "timestamp": result.conversation_log.timestamp.isoformat(),
                    "path_description": result.conversation_log.path_description,
                    "additional_facts": result.conversation_log.additional_facts,
                },
                "question_evaluations": [
                    {
                        "question_number": qa[0].question_number,
                        "question": qa[0].question,
                        "answer": qa[0].answer,
                        "metrics": {
                            "accuracy": qa[1].accuracy_score,
                            "completeness": qa[1].completeness_score,
                            "relevance": qa[1].relevance_score,
                            "clarity": qa[1].clarity_score,
                            "overall": qa[1].overall_score,
                        },
                    }
                    for qa in result.question_evaluations
                ],
                "average_metrics": {
                    "accuracy": result.average_metrics.accuracy_score,
                    "completeness": result.average_metrics.completeness_score,
                    "relevance": result.average_metrics.relevance_score,
                    "clarity": result.average_metrics.clarity_score,
                    "overall": result.average_metrics.overall_score,
                },
            }
            detailed_results.append(detailed_result)

        detailed_file = os.path.join(self.output_dir, f"detailed_evaluation_{timestamp}.json")
        with open(detailed_file, "w") as f:
            json.dump(detailed_results, f, indent=2)

        summary_file = os.path.join(self.output_dir, f"evaluation_summary_{timestamp}.json")
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"💾 Detailed results saved to: {detailed_file}")
        print(f"💾 Summary saved to: {summary_file}")

    def print_summary(self, summary: Dict[str, Any]) -> None:
        LINE = "=" * 60
        if "error" in summary:
            print(f"❌ {summary['error']}")
            return

        print("\n" + LINE)
        print("📊 EVALUATION SUMMARY")
        print(LINE)
        print(f"Total Conversations: {summary['total_conversations']}")
        print(f"Total Questions: {summary['total_questions']}\n")

        metrics = summary["overall_metrics"]
        print("Overall Metrics (0.0 - 1.0):")
        print(f"  🎯 Accuracy:     {metrics['accuracy']:.3f}")
        print(f"  ✅ Completeness: {metrics['completeness']:.3f}")
        print(f"  🔗 Relevance:    {metrics['relevance']:.3f}")
        print(f"  🔍 Clarity:      {metrics['clarity']:.3f}")
        print(f"  📈 Overall:      {metrics['overall']:.3f}\n")

        # Performance rating
        overall_score = metrics["overall"]
        if overall_score >= 0.8:
            rating = "🌟 Excellent"
        elif overall_score >= 0.6:
            rating = "👍 Good"
        elif overall_score >= 0.4:
            rating = "⚠️  Needs Improvement"
        else:
            rating = "❌ Poor"

        print(f"Performance Rating: {rating}")
        print(LINE)
