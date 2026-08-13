import styles from "./loading.module.css";

export default function Loading() {
  return (
    <main className={styles.container} aria-busy="true" aria-label="Loading sourced company analysis" role="status">
      <span className="sr-only">Loading sourced company analysis</span>
      <header className={styles.header} aria-hidden="true">
        <span className={`${styles.skeleton} ${styles.meta}`} />
        <span className={`${styles.skeleton} ${styles.title}`} />
        <span className={`${styles.skeleton} ${styles.price}`} />
        <span className={`${styles.skeleton} ${styles.source}`} />
      </header>
      <section className={styles.snapshot} aria-hidden="true">
        <span className={`${styles.skeleton} ${styles.sectionTitle}`} />
        <div className={styles.signalGrid}>
          {Array.from({ length: 4 }, (_, index) => (
            <div className={styles.signal} key={index}>
              <span className={`${styles.skeleton} ${styles.signalLabel}`} />
              <span className={`${styles.skeleton} ${styles.signalValue}`} />
              <span className={`${styles.skeleton} ${styles.signalDetail}`} />
            </div>
          ))}
        </div>
      </section>
      <section className={styles.contentGrid} aria-hidden="true">
        <div className={styles.panel}>
          <span className={`${styles.skeleton} ${styles.sectionTitle}`} />
          <span className={`${styles.skeleton} ${styles.chart}`} />
        </div>
        <div className={styles.panel}>
          <span className={`${styles.skeleton} ${styles.sectionTitle}`} />
          <span className={`${styles.skeleton} ${styles.rows}`} />
        </div>
      </section>
    </main>
  );
}
