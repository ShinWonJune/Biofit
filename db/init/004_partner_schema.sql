-- ---------------------------------------------------------------------------
-- 005_partner_schema.sql  |  BioFit Partner & Group Session 추천용 스키마 v2
-- ---------------------------------------------------------------------------
-- • users             : 회원 기본 정보 + 수면/기상 시간
-- • preferred_slots   : 회원별 다중 선호 운동 슬롯
-- • group_sessions    : 그룹 활동 스케줄
-- • match_history     : 매칭 이력
-- ---------------------------------------------------------------------------

-- ▼ 기존 테이블이 있으면 삭제 (의존성 고려하여 순서대로)
DROP TABLE IF EXISTS match_history    CASCADE;
DROP TABLE IF EXISTS preferred_slots  CASCADE;
DROP TABLE IF EXISTS group_sessions   CASCADE;
DROP TABLE IF EXISTS users            CASCADE;

-- ────────────────────────────────────────────────────────────────────────────
-- 1) users
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id         VARCHAR(10) PRIMARY KEY,
    name            TEXT        NOT NULL,
    workout_level   VARCHAR(10) NOT NULL,      -- High / Middle / Low
    sleep_time      TIME        NOT NULL,      -- 예) 22:00
    wake_time       TIME        NOT NULL,      -- 예) 08:00
    image_url       TEXT
);

-- ────────────────────────────────────────────────────────────────────────────
-- 2) preferred_slots  (유저별 다중 운동 선호 시간)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE preferred_slots (
    id           SERIAL PRIMARY KEY,
    user_id      VARCHAR(10) REFERENCES users(user_id) ON DELETE CASCADE,
    slot_start   TIME NOT NULL,
    slot_end     TIME NOT NULL
);

-- ────────────────────────────────────────────────────────────────────────────
-- 3) group_sessions
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE group_sessions (
    group_id     SERIAL PRIMARY KEY,
    session_name TEXT        NOT NULL,
    start_time   TIME        NOT NULL,
    end_time     TIME        NOT NULL,
    level        VARCHAR(10) NOT NULL,
    capacity     INT         NOT NULL DEFAULT 10,
    description  TEXT,
    image_url    TEXT
);

-- ────────────────────────────────────────────────────────────────────────────
-- 4) match_history
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE match_history (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(10) REFERENCES users(user_id) ON DELETE CASCADE,
    partner_id  VARCHAR(10) REFERENCES users(user_id),
    group_id    INT         REFERENCES group_sessions(group_id),
    matched_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────────────────────
-- 5) 더미 데이터 : users  (★ 한 줄씩 INSERT)
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO users (user_id, name, workout_level, sleep_time, wake_time, image_url)
VALUES ('U001', 'Charlie', 'High',   '22:00', '08:00',
        'https://images.pexels.com/photos/1954524/pexels-photo-1954524.jpeg');

INSERT INTO users (user_id, name, workout_level, sleep_time, wake_time, image_url)
VALUES ('U002', 'Jenney',  'Middle', '21:00', '08:00',
        'https://images.pexels.com/photos/866026/pexels-photo-866026.jpeg');

INSERT INTO users (user_id, name, workout_level, sleep_time, wake_time, image_url)
VALUES ('U003', 'Alex',    'High',   '22:00', '08:00',
        'https://images.pexels.com/photos/414029/pexels-photo-414029.jpeg');

INSERT INTO users (user_id, name, workout_level, sleep_time, wake_time, image_url)
VALUES ('U004', 'Mia',     'Low',    '23:00', '08:00',
        'https://images.pexels.com/photos/1552242/pexels-photo-1552242.jpeg');

-- ────────────────────────────────────────────────────────────────────────────
-- 6) 더미 데이터 : preferred_slots (유저당 2개 슬롯, 한 줄씩)
-- ────────────────────────────────────────────────────────────────────────────
-- U001 ───────────────────────────────────────────────────────────────────────
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U001', '10:00', '11:00');
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U001', '18:00', '19:00');

-- U002 ───────────────────────────────────────────────────────────────────────
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U002', '10:00', '11:00');
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U002', '18:00', '19:00');

-- U003 ───────────────────────────────────────────────────────────────────────
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U003', '10:00', '11:00');
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U003', '18:00', '19:00');

-- U004 ───────────────────────────────────────────────────────────────────────
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U004', '10:00', '11:00');
INSERT INTO preferred_slots (user_id, slot_start, slot_end)
VALUES ('U004', '18:00', '19:00');

-- ────────────────────────────────────────────────────────────────────────────
-- 7) 더미 데이터 : group_sessions (한 줄씩)
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO group_sessions
    (session_name, start_time, end_time, level, capacity,
     description, image_url)
VALUES
    ('Morning Yoga', '10:00', '11:00', 'Middle', 12,
     '하루를 개운하게 여는 아침 요가 클래스',
     'https://images.pexels.com/photos/3823039/pexels-photo-3823039.jpeg');

INSERT INTO group_sessions
    (session_name, start_time, end_time, level, capacity,
     description, image_url)
VALUES
    ('Evening HIIT', '18:00', '18:45', 'High', 15,
     '저녁 시간 고강도 인터벌 트레이닝',
     'https://images.pexels.com/photos/1552249/pexels-photo-1552249.jpeg');

INSERT INTO group_sessions
    (session_name, start_time, end_time, level, capacity,
     description, image_url)
VALUES
    ('Sunset Pilates', '18:00', '19:00', 'Low', 10,
     '근지구력·유연성을 길러주는 석양 필라테스',
     'https://images.pexels.com/photos/4324024/pexels-photo-4324024.jpeg');

-- ---------------------------------------------------------------------------
-- END OF FILE
-- ---------------------------------------------------------------------------
