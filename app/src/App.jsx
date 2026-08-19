import Logo from './components/Logo';
import FireRiskMap from './components/FireRiskMap';
import './App.css';

export default function App() {
  return (
    <div className="fg-app">
      <header className="fg-header">
        <Logo size={140} />
      </header>
      <main className="fg-main">
        <FireRiskMap />
      </main>
    </div>
  );
}
