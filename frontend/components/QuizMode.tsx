"use client";

import React, { useState } from "react";
import { generateQuiz, checkAnswer } from "@/lib/api";
import type { QuizQuestion } from "@/lib/api";

interface QuizModeProps {
  sessionId: string | null;
  hasSourcesReady: boolean;
  onError: (message: string) => void;
}

export default function QuizMode({
  sessionId,
  hasSourcesReady,
  onError,
}: QuizModeProps) {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    isCorrect: boolean;
    message: string;
    explanation: string;
  } | null>(null);
  const [score, setScore] = useState(0);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [quizComplete, setQuizComplete] = useState(false);

  const handleGenerate = async () => {
    if (!sessionId || !hasSourcesReady) {
      onError("Please upload at least one document first.");
      return;
    }

    setIsGenerating(true);
    setQuestions([]);
    setCurrentIndex(0);
    setScore(0);
    setAnsweredCount(0);
    setQuizComplete(false);
    setFeedback(null);
    setSelectedAnswer(null);

    try {
      const result = await generateQuiz(sessionId, 5);
      setQuestions(result.questions);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Quiz generation failed");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAnswer = async (option: string) => {
    if (!sessionId || isChecking || feedback) return;

    const letter = option.charAt(0);
    setSelectedAnswer(letter);
    setIsChecking(true);

    const current = questions[currentIndex];

    try {
      const result = await checkAnswer(
        sessionId,
        current.question,
        letter,
        current.correct,
        current.explanation
      );

      setFeedback({
        isCorrect: result.is_correct,
        message: result.feedback,
        explanation: result.explanation,
      });

      if (result.is_correct) {
        setScore((s) => s + 1);
      }
      setAnsweredCount((c) => c + 1);
    } catch {
      // Fallback: local check
      const isCorrect = letter === current.correct;
      setFeedback({
        isCorrect,
        message: isCorrect ? "Correct! ✓" : `Incorrect. The answer was ${current.correct}.`,
        explanation: current.explanation,
      });
      if (isCorrect) setScore((s) => s + 1);
      setAnsweredCount((c) => c + 1);
    } finally {
      setIsChecking(false);
    }
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex((i) => i + 1);
      setSelectedAnswer(null);
      setFeedback(null);
    } else {
      setQuizComplete(true);
    }
  };

  const currentQuestion = questions[currentIndex];

  // No questions yet — show generate button
  if (questions.length === 0) {
    return (
      <div className="quiz-empty">
        <div className="quiz-empty-icon">🧠</div>
        <h3>Quiz Mode</h3>
        <p>Test your understanding of the uploaded content.</p>
        <button
          className="quiz-generate-btn"
          onClick={handleGenerate}
          disabled={isGenerating || !hasSourcesReady}
          id="quiz-generate-btn"
        >
          {isGenerating ? (
            <>
              <span className="spinner" style={{ width: 16, height: 16 }} />
              Generating questions...
            </>
          ) : (
            "🎯 Generate Quiz"
          )}
        </button>
        {!hasSourcesReady && (
          <p className="quiz-hint">Upload a document first to enable quiz mode.</p>
        )}
      </div>
    );
  }

  // Quiz complete — show results
  if (quizComplete) {
    const percentage = Math.round((score / questions.length) * 100);
    return (
      <div className="quiz-complete">
        <div className="quiz-complete-icon">
          {percentage >= 80 ? "🏆" : percentage >= 60 ? "🎉" : "📚"}
        </div>
        <h3>Quiz Complete!</h3>
        <div className="quiz-score-display">
          <div className="quiz-score-number">{score}/{questions.length}</div>
          <div className="quiz-score-label">{percentage}% correct</div>
        </div>
        <div className="quiz-score-bar">
          <div
            className="quiz-score-fill"
            style={{
              width: `${percentage}%`,
              background: percentage >= 80
                ? "var(--accent-green)"
                : percentage >= 60
                ? "#D4772C"
                : "var(--accent-red)",
            }}
          />
        </div>
        <button
          className="quiz-generate-btn"
          onClick={handleGenerate}
          disabled={isGenerating}
        >
          {isGenerating ? "Generating..." : "🔄 Try Again"}
        </button>
      </div>
    );
  }

  // Active question
  return (
    <div className="quiz-active">
      {/* Progress */}
      <div className="quiz-header">
        <div className="quiz-progress-text">
          Question {currentIndex + 1} of {questions.length}
        </div>
        <div className="quiz-score-badge">
          Score: {score}/{answeredCount}
        </div>
      </div>
      <div className="quiz-progress-bar">
        <div
          className="quiz-progress-fill"
          style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }}
        />
      </div>

      {/* Question */}
      <div className="quiz-question-card">
        <h3 className="quiz-question-text">{currentQuestion.question}</h3>

        {/* Options */}
        <div className="quiz-options">
          {currentQuestion.options.map((option, i) => {
            const letter = option.charAt(0);
            const isSelected = selectedAnswer === letter;
            const isCorrect = feedback && letter === currentQuestion.correct;
            const isWrong = feedback && isSelected && !feedback.isCorrect;

            let optionClass = "quiz-option";
            if (isCorrect) optionClass += " correct";
            else if (isWrong) optionClass += " wrong";
            else if (isSelected) optionClass += " selected";

            return (
              <button
                key={i}
                className={optionClass}
                onClick={() => handleAnswer(option)}
                disabled={!!feedback || isChecking}
              >
                <span className="quiz-option-letter">{letter}</span>
                <span className="quiz-option-text">{option.slice(2).trim()}</span>
              </button>
            );
          })}
        </div>

        {/* Checking indicator */}
        {isChecking && (
          <div className="quiz-checking">
            <span className="spinner" style={{ width: 16, height: 16 }} />
            Checking...
          </div>
        )}

        {/* Feedback */}
        {feedback && (
          <div className={`quiz-feedback ${feedback.isCorrect ? "correct" : "wrong"}`}>
            <div className="quiz-feedback-icon">
              {feedback.isCorrect ? "✅" : "❌"}
            </div>
            <div className="quiz-feedback-content">
              <div className="quiz-feedback-message">{feedback.message}</div>
              {feedback.explanation && (
                <div className="quiz-feedback-explanation">{feedback.explanation}</div>
              )}
            </div>
          </div>
        )}

        {/* Next button */}
        {feedback && (
          <button className="quiz-next-btn" onClick={handleNext}>
            {currentIndex < questions.length - 1 ? "Next Question →" : "See Results →"}
          </button>
        )}
      </div>
    </div>
  );
}
