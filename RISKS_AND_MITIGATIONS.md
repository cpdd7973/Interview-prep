# Risk Assessment & Mitigation Strategies

## Hardware & Performance Risks

### 1. RAM Exhaustion (HIGH RISK)
**Risk**: System exceeds 2GB RAM budget, causing crashes or slowdowns.

**Mitigation**:
- Lazy load Whisper model (load on first transcription, unload after 5 min idle)
- Process audio in 30-second chunks, clear buffers immediately
- Limit ChromaDB collection to 500 questions per role
- Use SQLite with small connection pool (max 5 connections)
- Monitor RAM usage with psutil, log warnings at 1.5GB
- Implement graceful degradation (disable semantic search if RAM > 1.8GB)

**Detection**: Add RAM monitoring endpoint `/health/memory`

### 2. Whisper Transcription Latency (MEDIUM RISK)
**Risk**: Whisper tiny on CPU takes 5-10 seconds per 30-second audio chunk.

**Mitigation**:
- Use Whisper tiny (not base) - 300MB vs 500MB, faster inference
- Process audio in real-time streaming mode
- Show "AI is thinking..." indicator during transcription
- Set max audio chunk to 30 seconds
- Implement timeout (15 seconds) with fallback to "I didn't catch that"

**Fallback**: If transcription fails 3 times, offer to reschedule

### 3. Concurrent Interview Conflicts (MEDIUM RISK)
**Risk**: Two interviews scheduled at same time, RAM budget exceeded.

**Mitigation**:
- Admin dashboard shows conflict warnings before scheduling
- Prevent overlapping interviews (check DB before creating session)
- Sequential agent execution enforced by LangGraph
- APScheduler max_instances=1 prevents parallel job execution
- If conflict detected, suggest alternative time slots

**Detection**: Query active sessions before scheduling

### 4. Daily.co Free Tier Limits (MEDIUM RISK)
**Risk**: Free tier allows 5 concurrent rooms, 20 min per session.

**Mitigation**:
- Document upgrade path to paid tier ($99/month for unlimited)
- Implement room cleanup job (delete rooms after interview completes)
- Set interview duration limit to 45 minutes (within free tier)
- Monitor room count, warn admin at 4 active rooms
- Reuse rooms if possible (same room_id for rescheduled interviews)

**Fallback**: If room creation fails, email admin and candidate with apology

## API & External Service Risks

### 5. Groq API Rate Limits (HIGH RISK)
**Risk**: Free tier has request limits, could fail during interview.

**Mitigation**:
- Implement exponential backoff (1s, 2s, 4s, 8s)
- Automatic fallback to Gemini API on Groq failure
- Cache common responses (greetings, closing statements)
- Batch LLM calls where possible (evaluate multiple answers together)
- Monitor API usage, log warnings at 80% of daily limit

**Fallback**: Gemini API as secondary LLM (also free tier)

### 6. Edge-TTS Service Downtime (LOW RISK)
**Risk**: Edge-TTS cloud service unavailable.

**Mitigation**:
- Retry with exponential backoff (3 attempts)
- Fallback to text-only mode (display questions in UI)
- Cache synthesized audio for common phrases
- Implement health check before interview starts
- Notify candidate if voice mode unavailable

**Fallback**: Text-based interview mode

### 7. Gmail API Quota Limits (LOW RISK)
**Risk**: Gmail API has daily sending limits (500 emails/day for free).

**Mitigation**:
- Track daily email count in SQLite
- Warn admin at 400 emails sent
- Batch notifications where possible
- Use transactional email service (SendGrid) as fallback
- Implement email queue with retry logic

**Fallback**: Log email content to file, manual send by admin

### 8. Google Calendar API Failures (LOW RISK)
**Risk**: Calendar event creation fails.

**Mitigation**:
- Calendar is optional (interview works without it)
- Retry calendar creation 3 times
- Continue scheduling even if calendar fails
- Log failure and notify admin
- Candidate still receives email with interview link

**Fallback**: Email contains all details, calendar is bonus

## System Reliability Risks

### 9. Backend Restart During Interview (HIGH RISK)
**Risk**: Backend crashes or restarts, losing active interview state.

**Mitigation**:
- APScheduler SQLite jobstore persists jobs across restarts
- All interview state stored in SQLite (not in-memory)
- Frontend polls status every 30 seconds, detects backend restart
- Whisper model reloads automatically on first transcription
- LangGraph state persisted to SQLite after each step
- Implement graceful shutdown (SIGTERM handler)

**Recovery**: Interview resumes from last saved state

### 10. Network Interruption (MEDIUM RISK)
**Risk**: Candidate's internet drops during interview.

**Mitigation**:
- Daily.co handles reconnection automatically
- Frontend shows "Reconnecting..." message
- Transcript saved after each Q&A exchange
- Interview can resume from last question
- Set reconnection timeout to 5 minutes
- If timeout exceeded, mark session as INCOMPLETE

**Recovery**: Admin can manually reschedule

### 11. Database Corruption (LOW RISK)
**Risk**: SQLite database file corrupted.

**Mitigation**:
- Enable SQLite WAL mode (write-ahead logging)
- Daily automated backups (copy .db file)
- Implement database integrity check on startup
- Store backups in separate directory
- Keep last 7 days of backups

**Recovery**: Restore from most recent backup

## Interview Quality Risks

### 12. Poor Audio Quality (MEDIUM RISK)
**Risk**: Whisper can't transcribe due to background noise, accent, etc.

**Mitigation**:
- Implement confidence score check (Whisper returns confidence)
- If confidence < 0.6, ask candidate to repeat
- Provide audio quality tips in waiting screen
- Test microphone before interview starts (record 5-second sample)
- Allow candidate to type answer if audio fails 3 times

**Fallback**: Hybrid voice + text mode

### 13. Inappropriate Candidate Responses (LOW RISK)
**Risk**: Candidate uses offensive language or behaves inappropriately.

**Mitigation**:
- LLM prompt includes professional conduct guidelines
- Implement content filter on transcripts (basic keyword check)
- Log all transcripts for admin review
- AI interviewer can politely redirect conversation
- Admin can manually cancel interview from dashboard

**Escalation**: Flag transcript for manual review

### 14. AI Interviewer Hallucination (MEDIUM RISK)
**Risk**: LLM generates incorrect or nonsensical questions.

**Mitigation**:
- Use curated question bank (not generated on-the-fly)
- LLM only selects from pre-approved questions
- Follow-up questions validated against context
- Implement output validation (check for offensive content)
- Log all AI responses for quality monitoring
- Use temperature=0.7 (not too creative)

**Detection**: Admin reviews transcripts post-interview

### 15. Evaluation Bias (MEDIUM RISK)
**Risk**: LLM evaluation shows bias based on name, gender, etc.

**Mitigation**:
- Evaluation prompt emphasizes objectivity
- Remove PII from transcript before evaluation (replace names with "Candidate")
- Use structured rubric with clear criteria
- Multiple evaluation dimensions (not single score)
- Admin can override scores manually
- Log evaluation reasoning for audit

**Audit**: Periodic review of evaluation patterns

## Security & Privacy Risks

### 16. Unauthorized Access to Interviews (HIGH RISK)
**Risk**: Anyone with room URL can join interview.

**Mitigation**:
- Daily.co rooms are private by default
- Room URL is unique UUID (hard to guess)
- Implement room password (optional)
- Check candidate email before allowing entry
- Log all room access attempts
- Expire room URL after interview completes

**Enhancement**: Add email verification step

### 17. Data Privacy Compliance (HIGH RISK)
**Risk**: Storing candidate data without consent (GDPR, etc.).

**Mitigation**:
- Add privacy policy and terms of service
- Candidate consent checkbox before interview
- Implement data retention policy (delete after 90 days)
- Allow candidates to request data deletion
- Encrypt sensitive data in database
- Don't store audio files (only transcripts)
- Admin-only access to transcripts

**Compliance**: Consult legal counsel for production use

### 18. API Key Exposure (HIGH RISK)
**Risk**: API keys leaked in code or logs.

**Mitigation**:
- Use .env file (never commit to git)
- Add .env to .gitignore
- Rotate API keys quarterly
- Use environment variables in production
- Implement secrets management (e.g., AWS Secrets Manager)
- Sanitize logs (never log API keys)

**Detection**: Use git-secrets or similar tools

## Operational Risks

### 19. Admin Misconfiguration (MEDIUM RISK)
**Risk**: Admin schedules interview with wrong details.

**Mitigation**:
- Confirmation screen before scheduling
- Send confirmation email to admin
- Allow admin to edit/reschedule before interview
- Validate all inputs (email format, future date, etc.)
- Show preview of candidate email before sending
- Implement undo/cancel within 5 minutes of scheduling

**Recovery**: Admin can cancel and reschedule

### 20. Timezone Confusion (HIGH RISK)
**Risk**: Interview scheduled in wrong timezone.

**Mitigation**:
- Store all times in UTC in database
- Display times in candidate's local timezone
- Show timezone explicitly in all communications
- Admin selects timezone from dropdown
- Confirmation email shows time in both UTC and local
- Calendar event includes timezone

**Validation**: Show "Interview in X hours" countdown

## Monitoring & Alerting

### Critical Metrics to Monitor:
1. RAM usage (alert at 1.5GB)
2. Active interview count (alert at 2 concurrent)
3. API error rates (alert at 10% failure rate)
4. Transcription latency (alert if > 15 seconds)
5. Database size (alert at 1GB)
6. Scheduler job queue length (alert if > 10 pending)

### Health Check Endpoints:
- `/health` - Basic health check
- `/health/memory` - RAM usage
- `/health/scheduler` - APScheduler status
- `/health/apis` - External API connectivity

### Logging Strategy:
- INFO: Normal operations (interview started, completed)
- WARNING: Degraded performance (high RAM, slow transcription)
- ERROR: Failures requiring attention (API errors, crashes)
- CRITICAL: System-wide issues (database corruption, out of memory)

## Disaster Recovery Plan

### Scenario 1: Complete System Failure
1. Restore database from latest backup
2. Restart backend services
3. APScheduler reloads pending jobs
4. Email all affected candidates with apology and reschedule link

### Scenario 2: Data Loss
1. Restore from backup (max 24 hours data loss)
2. Identify affected interviews
3. Contact candidates to reschedule
4. Offer compensation (if commercial)

### Scenario 3: Security Breach
1. Immediately rotate all API keys
2. Audit access logs
3. Notify affected candidates
4. Implement additional security measures
5. Report to authorities if required

## Testing Strategy

### Unit Tests:
- Each MCP server tool
- Database CRUD operations
- Scheduler job execution
- LLM client fallback logic

### Integration Tests:
- End-to-end scheduling flow
- Interview activation at scheduled time
- Transcript logging and retrieval
- Evaluation and report generation

### Load Tests:
- 10 concurrent interviews (should fail gracefully)
- 100 scheduled interviews in database
- 1000 questions in question bank
- RAM usage under load

### Failure Tests:
- Backend restart during interview
- API failures (mock 500 errors)
- Database connection loss
- Network interruption simulation

## Production Readiness Checklist

- [ ] All API keys in environment variables
- [ ] Database backups automated
- [ ] Logging configured and tested
- [ ] Health check endpoints working
- [ ] Error handling in all critical paths
- [ ] RAM monitoring active
- [ ] Privacy policy and terms of service
- [ ] Admin documentation complete
- [ ] Candidate instructions clear
- [ ] Emergency contact info available

## Known Limitations

1. **Single admin only** - No multi-user admin dashboard
2. **No panel interviews** - Only 1-on-1 interviews supported
3. **English only** - No multi-language support
4. **No video** - Audio-only interviews
5. **No live monitoring** - Admin can't watch interview in progress
6. **No candidate authentication** - Anyone with link can join
7. **No interview recording** - Only transcripts saved
8. **No custom evaluation rubrics** - Fixed scoring dimensions

## Future Enhancements

1. Multi-admin support with role-based access
2. Panel interview mode (multiple AI interviewers)
3. Multi-language support (Whisper supports 99 languages)
4. Video interview option (Daily.co supports video)
5. Live interview monitoring dashboard
6. Candidate authentication via email OTP
7. Interview recording (with consent)
8. Customizable evaluation rubrics per role
9. Integration with ATS (Applicant Tracking Systems)
10. Mobile app for candidates

---

**Last Updated**: Phase 1 Complete
**Next Review**: After Phase 2 (MCP Servers) Complete
