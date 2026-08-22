-- Legacy dev DBs created conversation_id as uuid; production stream ids are text (c-{project}-{user}).
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_conversation_id_fkey;
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_conversation_id_fkey;

ALTER TABLE conversations
  ALTER COLUMN conversation_id TYPE text USING conversation_id::text;

ALTER TABLE messages
  ALTER COLUMN conversation_id TYPE text USING conversation_id::text;

ALTER TABLE runs
  ALTER COLUMN conversation_id TYPE text USING conversation_id::text;

ALTER TABLE audit_events
  ALTER COLUMN conversation_id TYPE text USING conversation_id::text;

ALTER TABLE messages
  ADD CONSTRAINT messages_conversation_id_fkey
  FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id);

ALTER TABLE runs
  ADD CONSTRAINT runs_conversation_id_fkey
  FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id);
