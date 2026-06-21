import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, useInView } from 'framer-motion'
import { useRef } from 'react'
import {
  Zap, Upload, MessageSquare, FileText, Search,
  ArrowRight, Star, Sun, Moon, ChevronDown
} from 'lucide-react'
import './LandingPage.css'

/* ── Scroll-animated wrapper ──────────────────────────────────── */
function FadeInWhenVisible({ children, delay = 0, direction = 'up', className = '' }) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-80px' })

  const directionMap = {
    up: { y: 60, x: 0 },
    down: { y: -60, x: 0 },
    left: { y: 0, x: -60 },
    right: { y: 0, x: 60 },
  }

  const offset = directionMap[direction] || directionMap.up

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, ...offset }}
      animate={isInView ? { opacity: 1, x: 0, y: 0 } : { opacity: 0, ...offset }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

/* ── Stagger container ────────────────────────────────────────── */
const staggerContainer = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.15,
      delayChildren: 0.2,
    },
  },
}

const staggerItem = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
  },
}

function LandingPage() {
  const [theme, setTheme] = useState(() => localStorage.getItem('justask_theme') || 'light')
  const navigate = useNavigate()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('justask_theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => prev === 'light' ? 'dark' : 'light')

  const steps = [
    {
      icon: <Upload size={32} />,
      number: '01',
      title: 'Upload Your PDF',
      description: 'Drag and drop any PDF document. We support files up to 50MB with instant processing.',
      color: '#ffeb3b',
    },
    {
      icon: <Search size={32} />,
      number: '02',
      title: 'AI Processes It',
      description: 'Our RAG pipeline chunks, embeds, and indexes your document in seconds for deep understanding.',
      color: '#00e5ff',
    },
    {
      icon: <MessageSquare size={32} />,
      number: '03',
      title: 'Just Ask Anything',
      description: 'Chat naturally with your document. Get instant answers with page-level citations.',
      color: '#ff6b6b',
    },
  ]

  const testimonials = [
    {
      name: 'Aarav Sharma',
      role: 'Research Scholar, IIT Delhi',
      quote: 'JustAsk saved me hours of reading dense research papers. I can query any section instantly!',
      rating: 5,
      avatar: 'AS',
    },
    {
      name: 'Priya Patel',
      role: 'Law Student, NLSIU Bangalore',
      quote: 'Parsing legal documents used to take days. Now I just upload and ask — it\'s revolutionary.',
      rating: 5,
      avatar: 'PP',
    },
    {
      name: 'Rohan Gupta',
      role: 'Data Scientist, Flipkart',
      quote: 'The citation feature is brilliant. Every answer links back to the exact page. Trustworthy AI.',
      rating: 5,
      avatar: 'RG',
    },
  ]

  const features = [
    { title: 'Blazing Fast', desc: 'Answers in under 2 seconds', icon: <Zap size={24} /> },
    { title: 'Cited Sources', desc: 'Every answer with page refs', icon: <FileText size={24} /> },
    { title: 'Multi-Doc', desc: 'Upload and chat with many PDFs', icon: <Upload size={24} /> },
    { title: 'Private & Secure', desc: 'Your data stays yours', icon: <Star size={24} /> },
  ]

  // Ref for the steps section
  const stepsRef = useRef(null)
  const stepsInView = useInView(stepsRef, { once: true, margin: '-100px' })

  const testimonialsRef = useRef(null)
  const testimonialsInView = useInView(testimonialsRef, { once: true, margin: '-100px' })

  return (
    <motion.div
      className="landing"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.4 } }}
    >
      {/* ── Navbar ────────────────────────────────────────────── */}
      <motion.nav
        className="landing-nav"
        id="landing-nav"
        initial={{ y: -80 }}
        animate={{ y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="landing-nav-inner">
          <div className="landing-nav-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <motion.div
              className="landing-nav-logo"
              whileHover={{ rotate: 20, scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
            >
              <Zap size={20} />
            </motion.div>
            <span className="landing-nav-name">Just Ask</span>
          </div>
          <div className="landing-nav-links">
            <a href="#how-it-works" className="landing-nav-link">How It Works</a>
            <a href="#testimonials" className="landing-nav-link">Testimonials</a>
            <motion.button
              className="theme-toggle-nav"
              onClick={toggleTheme}
              title="Toggle Theme"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9, rotate: 180 }}
              transition={{ duration: 0.3 }}
            >
              <AnimatePresence mode="wait">
                <motion.div
                  key={theme}
                  initial={{ rotate: -90, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={{ rotate: 90, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
                </motion.div>
              </AnimatePresence>
            </motion.button>
            <motion.button
              className="landing-cta-nav"
              onClick={() => navigate('/upload')}
              id="nav-get-started"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              Get Started <ArrowRight size={16} />
            </motion.button>
          </div>
        </div>
      </motion.nav>

      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="landing-hero" id="hero">
        <div className="landing-hero-content">
          <FadeInWhenVisible delay={0.3}>
            <div className="landing-hero-badge">
              <Zap size={14} /> AI-Powered Document Intelligence
            </div>
          </FadeInWhenVisible>

          <FadeInWhenVisible delay={0.5}>
            <h1 className="landing-hero-title">
              Stop Reading.<br />
              <motion.span
                className="landing-hero-highlight"
                initial={{ rotate: 0 }}
                animate={{ rotate: -1 }}
                transition={{ delay: 1, duration: 0.4, type: 'spring', stiffness: 200 }}
              >
                Just Ask.
              </motion.span>
            </h1>
          </FadeInWhenVisible>

          <FadeInWhenVisible delay={0.7}>
            <p className="landing-hero-subtitle">
              Upload any PDF and have a conversation with it. Our AI reads, understands, and answers your questions with precise citations — so you don&apos;t have to read a single page.
            </p>
          </FadeInWhenVisible>

          <FadeInWhenVisible delay={0.9}>
            <div className="landing-hero-actions">
              <motion.button
                className="landing-cta-hero"
                onClick={() => navigate('/upload')}
                id="hero-get-started"
                whileHover={{ scale: 1.03, x: 4, y: 4, boxShadow: 'none' }}
                whileTap={{ scale: 0.97 }}
              >
                Get Started — It&apos;s Free <ArrowRight size={20} />
              </motion.button>
            </div>
          </FadeInWhenVisible>

          <FadeInWhenVisible delay={1.1}>
            <div className="landing-hero-stats">
              <div className="landing-stat">
                <span className="landing-stat-number">500+</span>
                <span className="landing-stat-label">Documents Processed</span>
              </div>
              <div className="landing-stat-divider" />
              <div className="landing-stat">
                <span className="landing-stat-number">&lt;2s</span>
                <span className="landing-stat-label">Avg Response Time</span>
              </div>
              <div className="landing-stat-divider" />
              <div className="landing-stat">
                <span className="landing-stat-number">99%</span>
                <span className="landing-stat-label">Citation Accuracy</span>
              </div>
            </div>
          </FadeInWhenVisible>
        </div>

        <FadeInWhenVisible delay={0.6} direction="right">
          <div className="landing-hero-visual">
            <motion.div
              className="hero-mockup"
              initial={{ rotate: 2 }}
              animate={{ rotate: 0 }}
              transition={{ delay: 1, duration: 0.5, type: 'spring' }}
            >
              <div className="hero-mockup-header">
                <div className="hero-mockup-dot" style={{ background: '#ff5f57' }} />
                <div className="hero-mockup-dot" style={{ background: '#ffbd2e' }} />
                <div className="hero-mockup-dot" style={{ background: '#28c840' }} />
                <span className="hero-mockup-title">JustAsk — Chat</span>
              </div>
              <div className="hero-mockup-body">
                <motion.div
                  className="hero-mockup-msg user-msg"
                  initial={{ opacity: 0, x: 30 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 1.2, duration: 0.4 }}
                >
                  <span>Summarize chapter 3 of this paper</span>
                </motion.div>
                <motion.div
                  className="hero-mockup-msg ai-msg"
                  initial={{ opacity: 0, x: -30 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 1.6, duration: 0.4 }}
                >
                  <span>Chapter 3 discusses the neural architecture search methodology, focusing on...</span>
                </motion.div>
                <motion.div
                  className="hero-mockup-source"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 2, duration: 0.3 }}
                >
                  <FileText size={12} /> Page 14 — 94% relevance
                </motion.div>
              </div>
            </motion.div>
          </div>
        </FadeInWhenVisible>

        <motion.a
          href="#how-it-works"
          className="landing-scroll-hint"
          animate={{ y: [0, 10, 0] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        >
          <ChevronDown size={24} />
        </motion.a>
      </section>

      {/* ── Features Strip ──────────────────────────────────── */}
      <FadeInWhenVisible>
        <section className="landing-features-strip">
          <div className="landing-features-inner">
            {features.map((f, i) => (
              <motion.div
                key={i}
                className="landing-feature-item"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.4 }}
              >
                <motion.div
                  className="landing-feature-icon"
                  whileHover={{ rotate: 10, scale: 1.2 }}
                >
                  {f.icon}
                </motion.div>
                <div>
                  <div className="landing-feature-title">{f.title}</div>
                  <div className="landing-feature-desc">{f.desc}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      </FadeInWhenVisible>

      {/* ── How It Works ────────────────────────────────────── */}
      <section className="landing-how" id="how-it-works">
        <FadeInWhenVisible>
          <div className="landing-section-header">
            <span className="landing-section-tag">How It Works</span>
            <h2 className="landing-section-title">Three Steps to Knowledge</h2>
            <p className="landing-section-sub">From document upload to instant answers — here&apos;s the magic behind JustAsk.</p>
          </div>
        </FadeInWhenVisible>

        <motion.div
          className="landing-steps"
          ref={stepsRef}
          variants={staggerContainer}
          initial="hidden"
          animate={stepsInView ? 'visible' : 'hidden'}
        >
          {steps.map((step, i) => (
            <motion.div
              key={i}
              className="landing-step-card"
              style={{ '--step-color': step.color }}
              variants={staggerItem}
              whileHover={{
                x: 4, y: 4, boxShadow: 'none',
                backgroundColor: step.color,
                color: '#000',
                transition: { duration: 0.15 },
              }}
            >
              <div className="landing-step-number">{step.number}</div>
              <div className="landing-step-icon">{step.icon}</div>
              <h3 className="landing-step-title">{step.title}</h3>
              <p className="landing-step-desc">{step.description}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── Testimonials ────────────────────────────────────── */}
      <section className="landing-testimonials" id="testimonials">
        <FadeInWhenVisible>
          <div className="landing-section-header">
            <span className="landing-section-tag">Testimonials</span>
            <h2 className="landing-section-title">Loved by Students &amp; Professionals</h2>
            <p className="landing-section-sub">See what people are saying about JustAsk.</p>
          </div>
        </FadeInWhenVisible>

        <motion.div
          className="landing-testimonial-grid"
          ref={testimonialsRef}
          variants={staggerContainer}
          initial="hidden"
          animate={testimonialsInView ? 'visible' : 'hidden'}
        >
          {testimonials.map((t, i) => (
            <motion.div
              key={i}
              className="landing-testimonial-card"
              variants={staggerItem}
              whileHover={{
                x: 4, y: 4, boxShadow: 'none',
                transition: { duration: 0.15 },
              }}
            >
              <div className="landing-testimonial-stars">
                {Array.from({ length: t.rating }).map((_, j) => (
                  <motion.div
                    key={j}
                    initial={{ opacity: 0, scale: 0 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.5 + j * 0.08, type: 'spring', stiffness: 300 }}
                  >
                    <Star size={16} fill="currentColor" />
                  </motion.div>
                ))}
              </div>
              <p className="landing-testimonial-quote">&ldquo;{t.quote}&rdquo;</p>
              <div className="landing-testimonial-author">
                <motion.div
                  className="landing-testimonial-avatar"
                  whileHover={{ scale: 1.15, rotate: -5 }}
                >
                  {t.avatar}
                </motion.div>
                <div>
                  <div className="landing-testimonial-name">{t.name}</div>
                  <div className="landing-testimonial-role">{t.role}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── Final CTA ───────────────────────────────────────── */}
      <FadeInWhenVisible>
        <section className="landing-final-cta">
          <h2>Ready to Stop Reading?</h2>
          <p>Join hundreds of users who save hours every week with JustAsk.</p>
          <motion.button
            className="landing-cta-hero"
            onClick={() => navigate('/upload')}
            whileHover={{ scale: 1.03, x: 6, y: 6, boxShadow: 'none' }}
            whileTap={{ scale: 0.97 }}
          >
            Launch App Now <ArrowRight size={20} />
          </motion.button>
        </section>
      </FadeInWhenVisible>

      {/* ── Footer ──────────────────────────────────────────── */}
      <FadeInWhenVisible>
        <footer className="landing-footer" id="footer">
          <div className="landing-footer-inner">
            <div className="landing-footer-brand">
              <div className="landing-nav-logo">
                <Zap size={18} />
              </div>
              <span>Just Ask</span>
            </div>
            <div className="landing-footer-credit">
              Created by <strong>Shivam Mishra</strong> @ NIT Patna 2025
            </div>
            <div className="landing-footer-links">
              <a href="#hero">Home</a>
              <a href="#how-it-works">How It Works</a>
              <a href="#testimonials">Reviews</a>
            </div>
          </div>
        </footer>
      </FadeInWhenVisible>
    </motion.div>
  )
}

export default LandingPage
