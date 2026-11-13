package ru.first100days;

import jakarta.servlet.http.HttpSession;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ProgramController {
    private static final String PROGRESS = "route-progress";
    private static final List<String> STEPS = List.of("resume", "reply", "interview", "review");
    private static final List<Material> MATERIALS = List.of(
        new Material("plan", "Личный план", "Шаблон на первые недели: цель, сроки и люди, к которым можно обратиться.", "txt", "План"),
        new Material("budget", "Бюджет на месяц", "Учебный бюджет в таблице. Распредели доход и посмотри, сколько останется.", "csv", "Деньги"),
        new Material("bill", "Учебная квитанция", "Пример с показаниями счётчика, тарифом и объяснением строк.", "txt", "Дом"),
        new Material("resume", "Резюме и отклик", "Шаблон первого резюме, короткий отклик и вопросы для тренировки.", "txt", "Работа")
    );

    private final String contactEmail;

    public ProgramController(@Value("${program.contact-email}") String contactEmail) {
        this.contactEmail = contactEmail;
    }

    @GetMapping("/program")
    public Program program() {
        return new Program(MATERIALS, contactEmail);
    }

    @GetMapping("/materials/{id}/download")
    public ResponseEntity<Resource> download(@PathVariable String id) {
        Material material = MATERIALS.stream()
            .filter(item -> item.id().equals(id))
            .findFirst()
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        String filename = material.id() + "." + material.format();
        String type = material.format().equals("csv") ? "text/csv" : "text/plain";
        return ResponseEntity.ok()
            .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment().filename(filename).build().toString())
            .contentType(new MediaType(MediaType.parseMediaType(type), StandardCharsets.UTF_8))
            .body(new ClassPathResource("materials/" + filename));
    }

    @GetMapping("/progress")
    public ResponseEntity<Progress> progress(HttpSession session) {
        Object saved = session.getAttribute(PROGRESS);
        Progress progress = saved instanceof Progress value ? value : new Progress(List.of());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(progress);
    }

    @PutMapping(value = "/progress", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Progress> updateProgress(@RequestBody Progress progress, HttpSession session) {
        List<String> completed = progress.completed();
        if (completed == null || completed.size() > STEPS.size() || completed.stream().anyMatch(step -> step == null || !STEPS.contains(step))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown route step");
        }

        Progress saved = new Progress(STEPS.stream().filter(completed::contains).toList());
        session.setAttribute(PROGRESS, saved);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(saved);
    }

    public record Material(String id, String title, String description, String format, String category) {}
    public record Program(List<Material> materials, String contactEmail) {}
    public record Progress(List<String> completed) {}
}