import { Routes, Route } from "react-router-dom";
import { UserProvider } from "./context/UserContext";
import { LanguageProvider } from "./i18n/LanguageContext";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import AppLayout from "./components/layout/AppLayout";
import LandingPage from "./features/landing/LandingPage";
import RequestAccessPage from "./features/landing/RequestAccessPage";
import LoginPage from "./features/auth/LoginPage";
import DashboardPage from "./features/dashboard/DashboardPage";
import WorklistPage from "./features/worklist/WorklistPage";
import UrgentInboxPage from "./features/worklist/UrgentInboxPage";
import PatientsPage from "./features/patients/PatientsPage";
import PatientProfilePage from "./features/patients/PatientProfilePage";
import ReferralsPage from "./features/referrals/ReferralsPage";
import ConsultationsPage from "./features/consultations/ConsultationsPage";
import MeasuresPage from "./features/measures/MeasuresPage";
import FacilitiesPage from "./features/facilities/FacilitiesPage";
import PatientLinkGate from "./features/patient/PatientLinkGate";
import AssistedPatientResponsePage from "./features/patient/AssistedPatientResponsePage";
import HelpSupportPage from "./features/help-support/HelpSupportPage";
import UserGuidePage from "./features/help-support/UserGuidePage";
import ContactSupportPage from "./features/help-support/ContactSupportPage";
import PrivacySecurityPage from "./features/help-support/PrivacySecurityPage";
import SettingsPage from "./features/settings/SettingsPage";
import AIReviewPage from "./features/ai/AIReviewPage";

function App() {
  return (
    <LanguageProvider>
      <UserProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/request-access" element={<RequestAccessPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/assisted-response" element={<AssistedPatientResponsePage />} />
          <Route path="/p/:linkToken" element={<PatientLinkGate />} />
          <Route element={<AppLayout />}>
            <Route element={<ProtectedRoute permission="dashboard" />}><Route path="/dashboard" element={<DashboardPage />} /></Route>
            <Route element={<ProtectedRoute permission="worklist" />}><Route path="worklist" element={<WorklistPage />} /></Route>
            <Route element={<ProtectedRoute permission="urgent_inbox" />}><Route path="urgent-inbox" element={<UrgentInboxPage />} /></Route>
            <Route element={<ProtectedRoute permission="patients" />}><Route path="patients" element={<PatientsPage />} /><Route path="patients/:patientId" element={<PatientProfilePage />} /></Route>
            <Route element={<ProtectedRoute permission="referrals" />}><Route path="referrals" element={<ReferralsPage />} /></Route>
            <Route element={<ProtectedRoute permission="consultations" />}><Route path="consultations" element={<ConsultationsPage />} /></Route>
            <Route element={<ProtectedRoute permission="ai_review" />}><Route path="ai-review" element={<AIReviewPage />} /></Route>
            <Route element={<ProtectedRoute permission="measures" />}><Route path="measures" element={<MeasuresPage />} /></Route>
            <Route element={<ProtectedRoute permission="facilities" />}><Route path="facilities" element={<FacilitiesPage />} /></Route>
            <Route element={<ProtectedRoute permission="settings" />}><Route path="settings" element={<SettingsPage />} /></Route>
            <Route path="help-support" element={<HelpSupportPage />} /><Route path="help-support/user-guide" element={<UserGuidePage />} /><Route path="help-support/contact" element={<ContactSupportPage />} /><Route path="help-support/privacy-security" element={<PrivacySecurityPage />} />
          </Route>
        </Routes>
      </UserProvider>
    </LanguageProvider>
  );
}
export default App;
