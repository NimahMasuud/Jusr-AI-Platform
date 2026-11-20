import { useEffect, useState } from "react";
import {
  acknowledgePatientInformation,
  getPatientPortalContext,
  reportPatientNotExplained,
  requestPatientCallback,
  submitPatientConfidence,
  submitPatientReassurance,
  submitPatientUnderstanding,
} from "./patientAccessService";
import type { PatientPortalContext } from "./patientAccessService";
import {
  ShieldCheck,
  CheckCircle2,
  Circle,
  CalendarDays,
  Phone,
  Info,
} from "lucide-react";
import "./patient.css";
import jusrLogo from "../../assets/jusr-logo-cropped.png";

type Language = "en" | "ar";

const translations = {
  en: {
    secureAccess: "Secure patient access",
    loading: "Loading your secure patient page...",
    loadError:
      "We could not load this patient page. Please check the link or contact your healthcare team.",
    submitError: "Your responses could not be submitted. Please try again.",
    facility: "Healthcare facility",
    due: "Please complete the next step by",
    simulated: "SIMULATED DATA — This is a demonstration experience.",
    eyebrow: "YOUR PERSONAL CARE PAGE",
    hello: "Hello, Patient A",
    welcome:
      "Your screening result has been reviewed. Here is an update on your care and what happens next.",
    screeningUpdate: "YOUR SCREENING UPDATE",
    resultReviewed: "Your result has been reviewed",
    resultDescription:
      "A member of your healthcare team has reviewed your screening result. Please follow the next step below and contact your care team if you need an explanation.",
    nextStep: "Next step",
    confirmatoryTesting: "Confirmatory testing",
    journey: "YOUR JOURNEY",
    careProgress: "Your care progress",
    completed: "Completed",
    upcoming: "Upcoming",
    nextAppointment: "Next appointment",
    screeningCompleted: "Screening completed",
    resultReviewedStep: "Result reviewed",
    careFollowUp: "Care and follow-up",
    whatHappensNext: "What happens next?",
    nextDescription:
      "Your care team will guide you through the next step. Please contact them if you need assistance.",
    yourResponse: "YOUR RESPONSE",
    hearFromYou: "We want to hear from you",
    feedbackIntro:
      "Your feedback helps your care team understand how best to support you.",
    receivedQuestion: "Have you received this information?",
    acknowledged: "Information acknowledged",
    received: "I have received this information",
    understandingQuestion:
      "Do you understand what this result means and what happens next?",
    yes: "Yes",
    partly: "Partly",
    no: "No",
    confidenceQuestion: "How confident are you about what happens next?",
    confidenceHint: "1 means not confident; 5 means very confident.",
    notExplained: "Nobody explained this to me",
    callbackQuestion: "Would you like someone to call you?",
    callbackDescription:
      "Your care team can contact you to explain your result or answer questions.",
    callbackRequested: "Call-back requested",
    requestCallback: "Request a call-back",
    callbackRecorded:
      "Your request has been recorded in this demonstration. No actual call-back has been scheduled.",
    submit: "Submit responses",
    submitted: "Responses submitted",
    submitHint:
      "Please acknowledge receipt, select your understanding and provide a confidence rating before submitting.",
    thankYou: "Thank you for your response.",
    submittedNotice:
      "Your responses have been recorded in this demonstration. They have not been sent to your healthcare team.",
    submittedResponses: "Your submitted responses",
    informationReceived: "Information received",
    understanding: "Understanding",
    confidenceRating: "Confidence rating",
    callBackSummary: "Call-back requested",
    needHelp: "Need help or have questions?",
    helpDescription:
      "Your care team is available to explain your result and guide you through the next steps.",
    contactDetails: "Contact details will appear here.",
    reassuranceQuestion: "Do you feel safely guided so far?",
    reassuranceHint: "1 means not at all; 5 means very reassured.",
    reassuranceSubmit: "Send reassurance rating",
    reassuranceThanks: "Thank you — your rating has been recorded.",
    footer: "Jusr AI · Helping you stay informed about your care.",
  },

  ar: {
    secureAccess: "وصول آمن للمريض",
    loading: "جارٍ تحميل صفحة المريض الآمنة...",
    loadError:
      "تعذر تحميل صفحة المريض. يرجى التحقق من الرابط أو التواصل مع فريق الرعاية الصحية.",
    submitError: "تعذر إرسال ردودك. يرجى المحاولة مرة أخرى.",
    facility: "المنشأة الصحية",
    due: "يرجى إكمال الخطوة التالية قبل",
    simulated: "بيانات تجريبية — هذه تجربة توضيحية.",
    eyebrow: "صفحة الرعاية الشخصية الخاصة بك",
    hello: "مرحباً، المريض أ",
    welcome:
      "تمت مراجعة نتيجة الفحص الخاصة بك. إليك تحديثاً عن رعايتك والخطوة التالية.",
    screeningUpdate: "تحديث الفحص الخاص بك",
    resultReviewed: "تمت مراجعة نتيجتك",
    resultDescription:
      "قام أحد أعضاء فريق الرعاية الصحية بمراجعة نتيجة الفحص الخاصة بك. يرجى اتباع الخطوة التالية والتواصل مع فريق الرعاية إذا كنت بحاجة إلى توضيح.",
    nextStep: "الخطوة التالية",
    confirmatoryTesting: "فحص تأكيدي",
    journey: "رحلتك الصحية",
    careProgress: "تقدم الرعاية الخاصة بك",
    completed: "مكتمل",
    upcoming: "قادم",
    nextAppointment: "الموعد التالي",
    screeningCompleted: "اكتمل الفحص",
    resultReviewedStep: "تمت مراجعة النتيجة",
    careFollowUp: "الرعاية والمتابعة",
    whatHappensNext: "ماذا سيحدث بعد ذلك؟",
    nextDescription:
      "سيرشدك فريق الرعاية خلال الخطوة التالية. يرجى التواصل معهم إذا كنت بحاجة إلى المساعدة.",
    yourResponse: "ردك",
    hearFromYou: "نود معرفة رأيك",
    feedbackIntro: "تساعد ملاحظاتك فريق الرعاية على فهم أفضل طريقة لدعمك.",
    receivedQuestion: "هل استلمت هذه المعلومات؟",
    acknowledged: "تم تأكيد استلام المعلومات",
    received: "لقد استلمت هذه المعلومات",
    understandingQuestion: "هل تفهم معنى هذه النتيجة وما الذي سيحدث بعد ذلك؟",
    yes: "نعم",
    partly: "جزئياً",
    no: "لا",
    confidenceQuestion: "ما مدى ثقتك بشأن الخطوة التالية؟",
    confidenceHint: "١ تعني غير واثق؛ ٥ تعني واثق جداً.",
    notExplained: "لم يشرح لي أحد هذه المعلومات",
    callbackQuestion: "هل ترغب في أن يتصل بك أحد؟",
    callbackDescription:
      "يمكن لفريق الرعاية الاتصال بك لشرح نتيجتك أو الإجابة عن أسئلتك.",
    callbackRequested: "تم طلب معاودة الاتصال",
    requestCallback: "طلب معاودة الاتصال",
    callbackRecorded:
      "تم تسجيل طلبك في هذه التجربة التوضيحية. لم يتم تحديد موعد اتصال فعلي.",
    submit: "إرسال الردود",
    submitted: "تم إرسال الردود",
    submitHint:
      "يرجى تأكيد استلام المعلومات وتحديد مدى فهمك وتقييم مستوى ثقتك قبل الإرسال.",
    thankYou: "شكراً لك على ردك.",
    submittedNotice:
      "تم تسجيل ردودك في هذه التجربة التوضيحية. لم يتم إرسالها إلى فريق الرعاية الصحية.",
    submittedResponses: "الردود التي قدمتها",
    informationReceived: "استلام المعلومات",
    understanding: "مدى الفهم",
    confidenceRating: "تقييم الثقة",
    callBackSummary: "طلب معاودة الاتصال",
    needHelp: "هل تحتاج إلى مساعدة أو لديك أسئلة؟",
    helpDescription:
      "فريق الرعاية متاح لشرح نتيجتك وإرشادك خلال الخطوات التالية.",
    contactDetails: "ستظهر تفاصيل الاتصال هنا.",
    reassuranceQuestion: "هل تشعر أنك في أيدٍ أمينة حتى الآن؟",
    reassuranceHint: "١ تعني لا على الإطلاق؛ ٥ تعني مطمئن جداً.",
    reassuranceSubmit: "إرسال تقييم الاطمئنان",
    reassuranceThanks: "شكراً لك — تم تسجيل تقييمك.",
    footer: "Jusr AI · نساعدك على متابعة رعايتك الصحية.",
  },
} as const;

interface PatientPageProps {
  linkToken: string;
  sessionToken: string | null;
}

const ARABIC_STEP_LABELS: Record<string, string> = {
  RESULT_RECEIVED: "تم استلام النتيجة",
  DOCTOR_REVIEWED: "راجع الطبيب النتيجة",
  APPOINTMENT: "الموعد",
  TREATMENT_OR_MONITORING: "العلاج أو المتابعة",
};

function PatientPage({ linkToken, sessionToken }: PatientPageProps) {
  const [portal, setPortal] = useState<PatientPortalContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [language, setLanguage] = useState<Language>("en");

  const t = translations[language];
  const isArabic = language === "ar";

  const formatNumber = (value: number) => {
    if (language === "ar") {
      const arabicDigits = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];

      return String(value).replace(
        /\d/g,
        (digit) => arabicDigits[Number(digit)],
      );
    }

    return String(value);
  };

  const [acknowledged, setAcknowledged] = useState(false);
  const [understanding, setUnderstanding] = useState<
    "Yes" | "Partly" | "No" | ""
  >("");
  const [confidence, setConfidence] = useState<number | null>(null);
  const [notExplained, setNotExplained] = useState(false);
  const [callbackRequested, setCallbackRequested] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [reassuranceRating, setReassuranceRating] = useState<number | null>(null);
  const [reassuranceSubmitted, setReassuranceSubmitted] = useState(false);
  const [reassuranceSaving, setReassuranceSaving] = useState(false);
  const [submittedResponse, setSubmittedResponse] = useState<{
    acknowledged: boolean;
    understanding: string;
    confidence: number;
    notExplained: boolean;
    callbackRequested: boolean;
    submittedAt: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    async function loadPortal() {
      try {
        setLoading(true);
        setLoadError("");
        const data = await getPatientPortalContext(linkToken, sessionToken);
        if (!active) return;
        setPortal(data);
        setLanguage(data.language === "ar" ? "ar" : "en");
        setAcknowledged(data.responses.acknowledged);
        if (data.responses.understood === "YES") {
          setUnderstanding("Yes");
        } else if (data.responses.understood === "PARTLY") {
          setUnderstanding("Partly");
        } else if (data.responses.understood === "NO") {
          setUnderstanding("No");
        }
        setConfidence(data.responses.confidence);
        setNotExplained(data.responses.explanationStatus === "NOT_EXPLAINED");
        setCallbackRequested(data.responses.callbackRequested);
      } catch {
        if (active) setLoadError(translations.en.loadError);
      } finally {
        if (active) setLoading(false);
      }
    }
    loadPortal();
    return () => {
      active = false;
    };
  }, [linkToken, sessionToken]);

  const canSubmit =
    acknowledged &&
    understanding !== "" &&
    confidence !== null &&
    !submitted &&
    !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      await acknowledgePatientInformation(linkToken, sessionToken);
      await submitPatientUnderstanding(
        linkToken,
        sessionToken,
        understanding === "Yes" ? "YES" : understanding === "Partly" ? "PARTLY" : "NO",
      );
      await submitPatientConfidence(linkToken, sessionToken, confidence!);
      // R-31: Partly/No must create the NOT_EXPLAINED follow-up task.
      if (notExplained || understanding !== "Yes") {
        await reportPatientNotExplained(linkToken, sessionToken);
      }
      if (callbackRequested) {
        await requestPatientCallback(linkToken, sessionToken);
      }
      const patientResponse = {
        acknowledged,
        understanding,
        confidence: confidence!,
        notExplained: notExplained || understanding !== "Yes",
        callbackRequested,
        submittedAt: new Date().toISOString(),
      };
      setSubmittedResponse(patientResponse);
      setSubmitted(true);
      setPortal(await getPatientPortalContext(linkToken, sessionToken));
    } catch {
      setSubmitError(t.submitError);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReassurance = async () => {
    if (reassuranceRating === null || reassuranceSubmitted) return;
    setReassuranceSaving(true);
    setSubmitError("");
    try {
      await submitPatientReassurance(linkToken, sessionToken, reassuranceRating);
      setReassuranceSubmitted(true);
    } catch {
      setSubmitError(t.submitError);
    } finally {
      setReassuranceSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="patient-page" dir="ltr">
        <div className="patient-content">
          <p role="status">{t.loading}</p>
        </div>
      </main>
    );
  }

  if (loadError || !portal) {
    return (
      <main className="patient-page" dir="ltr">
        <div className="patient-content">
          <p role="alert">{loadError || t.loadError}</p>
        </div>
      </main>
    );
  }

  const displayName = portal.patient.displayLabel;
  const screeningLabel = portal.screening?.displayLabel || t.resultReviewed;
  const nextActionLabel = portal.nextAction?.label || t.confirmatoryTesting;

  const progressSteps = portal.progress?.steps.length
    ? portal.progress.steps.map((step, index) => ({
        label:
          language === "ar"
            ? ARABIC_STEP_LABELS[step.key] ?? step.label
            : step.label,
        completed: step.done,
        current: index === portal.progress.currentStep && !step.done,
      }))
    : [
        { label: t.screeningCompleted, completed: true, current: false },
        { label: t.resultReviewedStep, completed: true, current: false },
        { label: t.nextAppointment, completed: false, current: true },
        { label: t.careFollowUp, completed: false, current: false },
      ];

  return (
    <main
      className={`patient-page ${isArabic ? "patient-arabic" : ""}`}
      dir={isArabic ? "rtl" : "ltr"}
      lang={language}
    >
      <header className="patient-header">
        <div className="patient-brand">
          <img src={jusrLogo} alt="Jusr AI" />
        </div>

        <div
          className="patient-language-switch"
          role="group"
          aria-label="Select language"
          dir="ltr"
        >
          <button
            type="button"
            className={language === "en" ? "active" : ""}
            onClick={() => setLanguage("en")}
            aria-pressed={language === "en"}
          >
            English
          </button>

          <button
            type="button"
            className={language === "ar" ? "active" : ""}
            onClick={() => setLanguage("ar")}
            aria-pressed={language === "ar"}
          >
            العربية
          </button>
        </div>

        <div className="patient-header-secure">
          <ShieldCheck size={16} />
          <span>{t.secureAccess}</span>
        </div>
      </header>

      <div className="patient-simulation-notice">
        <Info size={16} />
        <span>{t.simulated}</span>
      </div>

      <div className="patient-content">
        <section className="patient-welcome">
          <span className="patient-eyebrow">{t.eyebrow}</span>
          <h1>{displayName || t.hello}</h1>
          <p>{t.welcome}</p>
        </section>

        <section className="patient-result-card">
          <div className="patient-section-heading">
            <div>
              <span className="patient-eyebrow">{t.screeningUpdate}</span>
              <h2>{screeningLabel}</h2>
            </div>
            <span className="patient-result-icon">
              <CheckCircle2 size={23} />
            </span>
          </div>

          <p> {t.resultDescription}</p>

          <div className="patient-urgency">
            <span>{t.nextStep}</span>
            <strong>{nextActionLabel}</strong>
            {portal.urgencyText && (
              <p className="patient-urgency-note">{portal.urgencyText}</p>
            )}
          </div>
        </section>

        <section className="patient-progress-card">
          <div className="patient-card-heading">
            <div>
              <span className="patient-eyebrow">{t.journey}</span>
              <h2>{t.careProgress}</h2>
            </div>
          </div>

          <div className="patient-progress-list">
            {progressSteps.map((step, index) => (
              <div className="patient-progress-step" key={step.label}>
                <div className="patient-progress-marker">
                  {step.completed ? (
                    <CheckCircle2 size={21} />
                  ) : step.current ? (
                    <span className="patient-current-marker" />
                  ) : (
                    <Circle size={21} />
                  )}

                  {index !== progressSteps.length - 1 && (
                    <span
                      className={`patient-progress-line ${
                        step.completed ? "completed" : ""
                      }`}
                    />
                  )}
                </div>

                <div className="patient-progress-label">
                  <strong>{step.label}</strong>
                  <span>
                    {step.completed
                      ? t.completed
                      : step.current
                        ? t.nextStep
                        : t.upcoming}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="patient-next-step-card">
          <div className="patient-card-heading">
            <CalendarDays size={20} />
            <h2>{t.whatHappensNext}</h2>
          </div>

          <strong>{nextActionLabel}</strong>
          <p>
            {t.facility}: {portal.facility.name}. {t.nextDescription}
          </p>
          {portal.dueAt && (
            <p>
              {t.due}{" "}
              {new Date(portal.dueAt).toLocaleDateString(
                language === "ar" ? "ar" : "en",
              )}
            </p>
          )}
        </section>

        <section className="patient-response-card">
          <span className="patient-eyebrow">{t.yourResponse}</span>
          <h2>{t.hearFromYou}</h2>
          <p className="patient-response-intro">{t.feedbackIntro}</p>

          <div className="patient-response-group">
            <h3>{t.receivedQuestion}</h3>

            <button
              type="button"
              disabled={submitted}
              className={`patient-acknowledge-button ${
                acknowledged ? "selected" : ""
              }`}
              onClick={() => setAcknowledged(!acknowledged)}
              aria-pressed={acknowledged}
            >
              {acknowledged ? <CheckCircle2 size={19} /> : <Circle size={19} />}
              {acknowledged ? t.acknowledged : t.received}
            </button>
          </div>

          <div className="patient-response-group">
            <h3>{t.understandingQuestion}</h3>

            <div className="patient-choice-list">
              {[
                { value: "Yes" as const, label: t.yes },
                { value: "Partly" as const, label: t.partly },
                { value: "No" as const, label: t.no },
              ].map((option) => (
                <button
                  type="button"
                  disabled={submitted}
                  key={option.value}
                  className={`patient-choice-button ${
                    understanding === option.value ? "selected" : ""
                  }`}
                  onClick={() => setUnderstanding(option.value)}
                  aria-pressed={understanding === option.value}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="patient-response-group">
            <h3>{t.confidenceQuestion}</h3>
            <p className="patient-response-hint">{t.confidenceHint}</p>

            <div className="patient-confidence-list">
              {[1, 2, 3, 4, 5].map((rating) => (
                <button
                  type="button"
                  disabled={submitted}
                  key={rating}
                  className={`patient-confidence-button ${
                    confidence === rating ? "selected" : ""
                  }`}
                  onClick={() => setConfidence(rating)}
                  aria-pressed={confidence === rating}
                  aria-label={`Confidence rating ${rating}`}
                >
                  {formatNumber(rating)}
                </button>
              ))}
            </div>
          </div>

          <div className="patient-response-group">
            <button
              type="button"
              disabled={submitted}
              className={`patient-not-explained-button ${
                notExplained ? "selected" : ""
              }`}
              onClick={() => setNotExplained(!notExplained)}
              aria-pressed={notExplained}
            >
              {notExplained ? "✓ " : ""}
              {t.notExplained}
            </button>
          </div>

          <div className="patient-response-group patient-callback-group">
            <div>
              <h3>{t.callbackQuestion}</h3>
              <p className="patient-response-hint">{t.callbackDescription}</p>
            </div>

            <button
              type="button"
              disabled={submitted}
              className="patient-callback-button"
              onClick={() => setCallbackRequested(!callbackRequested)}
            >
              <Phone size={17} />
              {callbackRequested ? t.callbackRequested : t.requestCallback}
            </button>

            {callbackRequested && (
              <p className="patient-feedback-message" role="status">
                {t.callbackRequested}
              </p>
            )}
          </div>

          <div className="patient-submit-area">
            <button
              type="button"
              className="patient-submit-button"
              disabled={!canSubmit}
              onClick={handleSubmit}
            >
              {submitting ? t.loading : submitted ? t.submitted : t.submit}
            </button>

            {submitError && (
              <p className="patient-verification-error" role="alert">
                {submitError}
              </p>
            )}
            {!submitted && (
              <p className="patient-submit-hint">{t.submitHint}</p>
            )}

            {submitted && submittedResponse && (
              <div className="patient-submit-success" role="status">
                <CheckCircle2 size={20} />

                <div className="patient-submission-details">
                  <strong>{t.thankYou}</strong>

                  <p>
                    {language === "ar"
                      ? "تم إرسال ردودك بنجاح إلى فريق الرعاية الصحية."
                      : "Your responses have been successfully sent to your healthcare team."}
                  </p>

                  <div className="patient-submission-summary">
                    <h4>{t.submittedResponses}</h4>

                    <div>
                      <span>{t.informationReceived}</span>
                      <strong>
                        {submittedResponse.acknowledged ? t.yes : t.no}
                      </strong>
                    </div>

                    <div>
                      <span>{t.understanding}</span>
                      <strong>
                        {submittedResponse.understanding === "Yes"
                          ? t.yes
                          : submittedResponse.understanding === "Partly"
                            ? t.partly
                            : t.no}
                      </strong>
                    </div>

                    <div>
                      <span>{t.confidenceRating}</span>
                      <strong dir="ltr">
                        {formatNumber(submittedResponse.confidence)} /{" "}
                        {formatNumber(5)}
                      </strong>
                    </div>

                    <div>
                      <span>{t.notExplained}</span>
                      <strong>
                        {submittedResponse.notExplained ? t.yes : t.no}
                      </strong>
                    </div>

                    <div>
                      <span>{t.callBackSummary}</span>
                      <strong>
                        {submittedResponse.callbackRequested ? t.yes : t.no}
                      </strong>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {portal.reassuranceAvailable && (
          <section className="patient-response-card patient-reassurance-card">
            <span className="patient-eyebrow">{t.yourResponse}</span>
            <h2>{t.reassuranceQuestion}</h2>
            <p className="patient-response-hint">{t.reassuranceHint}</p>

            <div className="patient-confidence-list">
              {[1, 2, 3, 4, 5].map((rating) => (
                <button
                  type="button"
                  key={rating}
                  disabled={reassuranceSubmitted || reassuranceSaving}
                  className={`patient-confidence-button ${
                    reassuranceRating === rating ? "selected" : ""
                  }`}
                  onClick={() => setReassuranceRating(rating)}
                  aria-pressed={reassuranceRating === rating}
                  aria-label={`Reassurance rating ${rating}`}
                >
                  {formatNumber(rating)}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="patient-submit-button"
              disabled={
                reassuranceRating === null ||
                reassuranceSubmitted ||
                reassuranceSaving
              }
              onClick={() => void handleReassurance()}
            >
              {reassuranceSubmitted
                ? t.submitted
                : reassuranceSaving
                  ? t.loading
                  : t.reassuranceSubmit}
            </button>

            {reassuranceSubmitted && (
              <p className="patient-feedback-message" role="status">
                {t.reassuranceThanks}
              </p>
            )}
          </section>
        )}

        <section className="patient-contact-card">
          <div className="patient-contact-icon">
            <Phone size={20} />
          </div>

          <div>
            <h3>{t.needHelp}</h3>
            <p>{t.helpDescription}</p>
            <span>{portal.contact?.name ?? portal.contact?.facility ?? t.contactDetails}</span>
            {portal.contact?.facility && portal.contact.name && (
              <span>{portal.contact.facility}</span>
            )}
            {portal.contact?.phone && (
              <strong dir="ltr" className="patient-contact-phone">
                {portal.contact.phone}
              </strong>
            )}
          </div>
        </section>
      </div>

      <footer className="patient-footer">
        <p>{t.footer}</p>
      </footer>
    </main>
  );
}

export default PatientPage;
