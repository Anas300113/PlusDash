CREATE TABLE IF NOT EXISTS plus11_learners (
  open_id VARCHAR(191) NOT NULL,
  display_name VARCHAR(80) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_practice_sessions (
  session_id CHAR(36) NOT NULL,
  learner_open_id VARCHAR(191) NOT NULL,
  idempotency_key CHAR(36) NOT NULL,
  subject_id VARCHAR(40) NOT NULL,
  topic_id VARCHAR(60) NOT NULL,
  activity_date DATE NOT NULL,
  question_index SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  total_questions SMALLINT UNSIGNED NOT NULL DEFAULT 8,
  duration_seconds INT UNSIGNED NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
  started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  completed_at DATETIME(3) NULL,
  PRIMARY KEY (session_id),
  UNIQUE KEY uq_p11_session_idem (learner_open_id, idempotency_key),
  KEY ix_p11_sessions_learner_date (learner_open_id, activity_date),
  KEY ix_p11_sessions_active (learner_open_id, status, started_at),
  CONSTRAINT fk_p11_sessions_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_practice_answers (
  answer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id CHAR(36) NOT NULL,
  learner_open_id VARCHAR(191) NOT NULL,
  question_id VARCHAR(80) NOT NULL,
  subject_id VARCHAR(40) NOT NULL,
  topic_id VARCHAR(60) NOT NULL,
  question_index SMALLINT UNSIGNED NOT NULL,
  attempt_number SMALLINT UNSIGNED NOT NULL,
  idempotency_key CHAR(36) NOT NULL,
  selected_answer VARCHAR(12) NOT NULL,
  is_correct TINYINT(1) NOT NULL,
  answered_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (answer_id),
  UNIQUE KEY uq_p11_answer_attempt (session_id, question_index, attempt_number),
  UNIQUE KEY uq_p11_answer_idem (learner_open_id, idempotency_key),
  KEY ix_p11_answers_learner_time (learner_open_id, answered_at),
  CONSTRAINT fk_p11_answers_session FOREIGN KEY (session_id) REFERENCES plus11_practice_sessions (session_id),
  CONSTRAINT fk_p11_answers_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_topic_mastery (
  learner_open_id VARCHAR(191) NOT NULL,
  subject_id VARCHAR(40) NOT NULL,
  topic_id VARCHAR(60) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  correct_count INT UNSIGNED NOT NULL DEFAULT 0,
  last_practiced_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (learner_open_id, topic_id),
  KEY ix_p11_mastery_subject (learner_open_id, subject_id),
  CONSTRAINT fk_p11_mastery_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_daily_activity (
  learner_open_id VARCHAR(191) NOT NULL,
  activity_date DATE NOT NULL,
  minutes_practiced INT UNSIGNED NOT NULL DEFAULT 0,
  answer_count INT UNSIGNED NOT NULL DEFAULT 0,
  correct_count INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (learner_open_id, activity_date),
  CONSTRAINT fk_p11_activity_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_plan_completions (
  learner_open_id VARCHAR(191) NOT NULL,
  activity_date DATE NOT NULL,
  activity_id VARCHAR(60) NOT NULL,
  completed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (learner_open_id, activity_date, activity_id),
  CONSTRAINT fk_p11_plan_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS plus11_review_items (
  card_id CHAR(36) NOT NULL,
  learner_open_id VARCHAR(191) NOT NULL,
  source_question_id VARCHAR(80) NOT NULL,
  subject_id VARCHAR(40) NOT NULL,
  topic_id VARCHAR(60) NOT NULL,
  prompt TEXT NOT NULL,
  answer TEXT NOT NULL,
  due_at DATETIME(3) NOT NULL,
  last_reviewed_at DATETIME(3) NULL,
  correct_streak INT UNSIGNED NOT NULL DEFAULT 0,
  review_count INT UNSIGNED NOT NULL DEFAULT 0,
  last_outcome VARCHAR(16) NULL,
  last_event_id CHAR(36) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (card_id),
  UNIQUE KEY uq_p11_review_source (learner_open_id, source_question_id),
  KEY ix_p11_review_due (learner_open_id, due_at),
  CONSTRAINT fk_p11_review_learner FOREIGN KEY (learner_open_id) REFERENCES plus11_learners (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
